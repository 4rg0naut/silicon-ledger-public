// granite-runner — numeric gate + latency benchmark for the Granite-Embedding-97M
// Core AI bundle (ModernBERT encoder, 384-d CLS-pooled).
//
// Two gates, both required:
//   1. TOKENIZER parity  — our encoding must equal the reference `input_ids`/`attention_mask`.
//   2. NUMERIC parity    — embedding cosine vs the HF oracle shipped in `reference.json`.
// The numeric gate is not optional: Core AI compute-unit *preferences* are documented to
// return silently wrong numerics on some graphs, so a placement without a gate is worthless.
//
// usage: granite-runner <bundle.aimodel> <tokenizerDir> <reference.json>
//                      [--compute cpuOnly|cpu|gpu|neuralEngine] [--iters N]

import CoreAIKitVision
import Dispatch
import Foundation

struct Fixture: Decodable {
    let id: String
    let text: String
    let kind: String
    let input_ids: [Int32]
    let attention_mask: [Int32]
    let embedding: [Float]
    let active_tokens: Int
    let original_tokens: Int
}

struct Reference: Decodable {
    let model_sha: String
    let sequence_length: Int
    let fixtures: [Fixture]
}

func now() -> Double { Double(DispatchTime.now().uptimeNanoseconds) / 1e9 }

func cosine(_ a: [Float], _ b: [Float]) -> Float {
    var dot: Float = 0, na: Float = 0, nb: Float = 0
    for i in 0..<min(a.count, b.count) {
        dot += a[i] * b[i]
        na += a[i] * a[i]
        nb += b[i] * b[i]
    }
    let d = (na.squareRoot() * nb.squareRoot())
    return d == 0 ? 0 : dot / d
}

func maxAbsErr(_ a: [Float], _ b: [Float]) -> Float {
    var m: Float = 0
    for i in 0..<min(a.count, b.count) { m = max(m, abs(a[i] - b[i])) }
    return m
}

@main
enum GraniteRunner {
    static func usage() -> Never {
        let text = "usage: granite-runner <bundle.aimodel> <tokenizerDir> <reference.json> "
            + "[--compute cpuOnly|cpu|gpu|neuralEngine] [--iters N]"
            + " [--dump-embeddings PATH] [--dump-latencies PATH]\n"
        FileHandle.standardError.write(Data(text.utf8))
        exit(2)
    }

    static func main() async throws {
        var args = Array(CommandLine.arguments.dropFirst())
        guard args.count >= 3 else { usage() }
        let bundleURL = URL(fileURLWithPath: args.removeFirst())
        let tokenizerDir = URL(fileURLWithPath: args.removeFirst())
        let referenceURL = URL(fileURLWithPath: args.removeFirst())

        var compute: GraphModel.ComputeUnits = .cpuOnly
        var iters = 105
        var dumpPath: String? = nil
        var latPath: String? = nil
        while !args.isEmpty {
            let flag = args.removeFirst()
            switch flag {
            case "--compute":
                guard let v = args.first else { usage() }
                args.removeFirst()
                switch v {
                case "cpuOnly": compute = .cpuOnly
                case "cpu": compute = .cpu
                case "gpu": compute = .gpu
                case "neuralEngine": compute = .neuralEngine
                default: usage()
                }
            case "--iters":
                guard let v = args.first, let n = Int(v) else { usage() }
                args.removeFirst()
                iters = n
            case "--dump-embeddings":
                guard let v = args.first else { usage() }
                args.removeFirst()
                dumpPath = v
            case "--dump-latencies":
                guard let v = args.first else { usage() }
                args.removeFirst()
                latPath = v
            default: usage()
            }
        }

        let ref = try JSONDecoder().decode(Reference.self, from: Data(contentsOf: referenceURL))
        let tokenizer = try GraniteTokenizer(
            tokenizerURL: tokenizerDir.appendingPathComponent("tokenizer.json"),
            tokenizerConfigURL: tokenizerDir.appendingPathComponent("tokenizer_config.json"))

        print("bundle       : \(bundleURL.lastPathComponent)")
        print("compute      : \(compute)")
        print("sequence len : \(ref.sequence_length)   fixtures: \(ref.fixtures.count)")

        let t0 = now()
        let model = try await GraphModel(contentsOf: bundleURL, function: "main", computeUnits: compute)
        let loadMs = (now() - t0) * 1000
        print("inputs       : \(model.inputNames)")
        print("outputs      : \(model.outputNames)")
        print(String(format: "load         : %.0f ms", loadMs))

        // ---- gates -------------------------------------------------------
        var minCos: Float = 1
        var maxErr: Float = 0
        var tokBad = 0
        var embBad = 0
        var firstRunMs = 0.0
        var dumped: [String: [Float]] = [:]

        for (index, f) in ref.fixtures.enumerated() {
            let enc = try tokenizer.encode(text: f.text, sequenceLength: ref.sequence_length)
            if enc.inputIDs != f.input_ids || enc.attentionMask != f.attention_mask { tokBad += 1 }

            let t = now()
            let out = try await model.run([
                "input_ids": .int32(enc.inputIDs, shape: [1, ref.sequence_length]),
                "attention_mask": .int32(enc.attentionMask, shape: [1, ref.sequence_length]),
            ])
            if index == 0 { firstRunMs = (now() - t) * 1000 }

            guard let emb = out["embedding"] else {
                FileHandle.standardError.write(Data("no 'embedding' output\n".utf8))
                exit(1)
            }
            let v = emb.floats()
            let c = cosine(v, f.embedding)
            let e = maxAbsErr(v, f.embedding)
            minCos = min(minCos, c)
            maxErr = max(maxErr, e)
            if c < 0.999 || e > 0.02 { embBad += 1 }
            dumped[f.id] = v
        }

        if let dumpPath {
            let data = try JSONSerialization.data(withJSONObject: dumped, options: [.sortedKeys])
            try data.write(to: URL(fileURLWithPath: dumpPath))
            print("embeddings   : dumped \(dumped.count) vectors -> \(dumpPath)")
        }

        print(String(format: "tokenizer    : %d/%d exact (mismatches %d)",
                     ref.fixtures.count - tokBad, ref.fixtures.count, tokBad))
        print(String(format: "numeric gate : min cosine %.9f | max |err| %.2e | failures %d/%d",
                     minCos, maxErr, embBad, ref.fixtures.count))
        print(String(format: "first after load : %.2f ms", firstRunMs))

        // ---- warm latency ------------------------------------------------
        let sampleText = ref.fixtures.first(where: { $0.kind == "document" })?.text
            ?? ref.fixtures.first?.text ?? "hello"
        let enc = try tokenizer.encode(text: sampleText, sequenceLength: ref.sequence_length)
        let input: [String: TensorValue] = [
            "input_ids": .int32(enc.inputIDs, shape: [1, ref.sequence_length]),
            "attention_mask": .int32(enc.attentionMask, shape: [1, ref.sequence_length]),
        ]
        for _ in 0..<5 { _ = try await model.run(input) }

        var samples: [Double] = []
        samples.reserveCapacity(iters)
        for _ in 0..<iters {
            let t = now()
            _ = try await model.run(input)
            samples.append((now() - t) * 1000)
        }
        samples.sort()
        let median = samples[samples.count / 2]
        let p95 = samples[min(samples.count - 1, Int(Double(samples.count) * 0.95))]

        print(String(format: "warm median  : %.2f ms | p95 %.2f ms | min %.2f ms | n=%d",
                     median, p95, samples[0], samples.count))
        if let latPath {
            // Raw per-inference series in acquisition order (not sorted): the ordering is what
            // distinguishes a periodic tail from a random one.
            let text = samples.map { String(format: "%.4f", $0) }.joined(separator: "\n")
            try text.write(toFile: latPath, atomically: true, encoding: .utf8)
            print("latencies    : dumped \(samples.count) samples -> \(latPath)")
        }
        let pass = (tokBad == 0 && embBad == 0)
        print("VERDICT      : compute=\(compute) gate=\(pass ? "PASS" : "FAIL") "
              + "median_ms=\(String(format: "%.3f", median))")
    }
}
