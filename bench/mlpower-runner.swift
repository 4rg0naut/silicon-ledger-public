// mlpower-runner.swift — Core ML inference load for power A/B, WITHOUT coremltools.
//
// Why. macOS 27 made Core AI the headline stack and the python coremltools wheel is not part of
// this workspace anymore, but the Core ML runtime itself is still here — and MLModel.compileModel
// (system API) covers the compilation step the missing coremlc CLI used to. This is the load
// side of power_ab.py re-hosted in Swift: load minilm128 (compiled .mlmodelc) on a chosen
// compute-unit budget, hammer it with the fixed 4-text MiniLM token set for N seconds, report
// completions so the driver can divide mean rail mW by measured rate (mJ/embedding).
//
// Build: swiftc -O bench/mlpower-runner.swift -o bench/mlpower-runner
// Run:   bench/mlpower-runner <model.mlmodelc> <all|cpuOnly> <seconds> <tokens.bin>
// tokens.bin: int32 LE: nseq, seq, then nseq*seq input_ids, then nseq*seq attention_mask.

import Foundation
import CoreML

guard CommandLine.arguments.count == 5 else {
    FileHandle.standardError.write(Data("usage: mlpower-runner <model.mlmodelc> <all|cpuOnly> <seconds> <tokens.bin>\n".utf8))
    exit(2)
}
let modelURL = URL(fileURLWithPath: CommandLine.arguments[1])
let mode = CommandLine.arguments[2]
let seconds = Double(CommandLine.arguments[3]) ?? 15.0
let tokensURL = URL(fileURLWithPath: CommandLine.arguments[4])

let raw = try! Data(contentsOf: tokensURL)
let words = raw.withUnsafeBytes { $0.bindMemory(to: Int32.self) }
let nseq = Int(words[0]), seq = Int(words[1])
precondition(nseq > 0 && seq > 0 && raw.count >= (2 + 2 * nseq * seq) * 4)

func multiArray(_ offset: Int, buffer out: inout MLMultiArray?) {
    let arr = try! MLMultiArray(shape: [1, NSNumber(value: seq)], dataType: .int32)
    let base = raw.withUnsafeBytes { $0.baseAddress!.advanced(by: offset * 4) }
    // copy so the MLMultiArray owns its memory
    memcpy(arr.dataPointer, base, seq * 4)
    out = arr
}

let cfg = MLModelConfiguration()
switch mode {
case "all": cfg.computeUnits = .all
case "cpuOnly": cfg.computeUnits = .cpuOnly
default:
    FileHandle.standardError.write(Data("bad mode \(mode)\n".utf8)); exit(2)
}
let model = try MLModel(contentsOf: modelURL, configuration: cfg)

var arrays: [(MLMultiArray, MLMultiArray)] = []
for i in 0..<nseq {
    var ids: MLMultiArray?, mask: MLMultiArray?
    multiArray(2 + i * seq, buffer: &ids)
    multiArray(2 + nseq * seq + i * seq, buffer: &mask)
    arrays.append((ids!, mask!))
}

func predict(_ pair: (MLMultiArray, MLMultiArray)) throws {
    let provider = try MLDictionaryFeatureProvider(dictionary: [
        "input_ids": MLFeatureValue(multiArray: pair.0),
        "attention_mask": MLFeatureValue(multiArray: pair.1),
    ])
    _ = try model.prediction(from: provider)
}

// warmup (10 rounds incl. ANE program load), then the measured window
for i in 0..<10 { try predict(arrays[i % nseq]) }
let t0 = Date()
var n = 0
while Date().timeIntervalSince(t0) < seconds {
    try predict(arrays[n % nseq])
    n += 1
}
let elapsed = Date().timeIntervalSince(t0)
print("mode=\(mode) n=\(n) elapsed=\(String(format: "%.3f", elapsed)) rate=\(String(format: "%.1f", Double(n) / elapsed)) emb/s")
