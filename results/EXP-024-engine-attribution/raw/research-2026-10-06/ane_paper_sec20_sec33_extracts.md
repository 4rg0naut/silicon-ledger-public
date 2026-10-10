# arXiv 2606.22283 chapter extracts — fetched 2026-10-06
# full html (5,420,904 B) pinned at exp024-raw/research-2026-10-06/ (MANIFEST.sha256)


## Chapter 1 — 1 overview (1.3 two core counts)

ltx_tag_chapter">Chapter 1 What the ANE is 

 
 
 SUMMARY 
 The Apple Neural Engine is a fixed-function fp16 matrix accelerator with
a wide accumulator, reachable directly below Core ML. The fp16 product
path and wide accumulator explain much of the engine’s numerical
behavior and contribute to its efficiency. It is faster than the GPU on
compute-bound vision and convolution, 3.8 times faster and 9 times more
efficient on a 256-channel 3x3 convolution; the GPU leads only on
bandwidth-bound decode. The overhead-isolated compute slope reaches near
12 fp16 TFLOP/s against 85 GB/s of DRAM bandwidth, with a 2 MB on-chip
working-set threshold as the primary design limit. 
 
 
 
 The Apple Neural Engine is a fixed-function matrix accelerator built
into every recent Apple system on chip, from the A11 and the M1 onward.
It runs the feed-forward neural networks of on-device perception, vision
and speech, at low power, and leaves the CPU and the GPU free for the
rest of the system. Apple distributes it in volume and documents almost
none of it. The engine is beside the CPU and the GPU on the same chip,
where the three share one pool of DRAM, as figure   1.1 shows. 
 
 
 Figure 1.1: The Apple Neural Engine beside the CPU and GPU on one chip, sharing unified DRAM. 
 
 
 1.1 Reachable surface 

 
 The public way to use the engine is Core ML
 [AppleCoreML] , whose load-and-predict
call shape Listing   1 shows. 
 
 
 List of listings 1 The Core ML load-and-predict path, where the compute-unit field is a placement hint rather than a guarantee. 
 
 
 // The public path: ask for the engine, but Core ML still places the work. 
 
 
 let config = MLModelConfiguration () 
 
 
 config . computeUnits = . cpuAndNeuralEngine // a hint, not a guarantee 
 
 
 let model = try MLModel ( contentsOf : url , configuration : config ) 
 
 
 let out = try model . prediction ( from : input ) // planner splits ops across CPU, GPU, ANE 
 
 
 // The caller is not told which device ran each segment. 
 
 
 
 A cost-driven placement planner segments a model handed to Core ML
across the CPU, GPU, and ANE. An eligibility check decides which
operations the engine can accept, and a roofline and transfer cost model
decides where each segment runs. The planner is opaque. A caller does
not choose the device and is not told which device ran the work. 
 
 
 A direct route reaches the engine without Core ML. The same private
Espresso runtime that Apple’s own dispatchers use is callable from
ordinary user space. It compiles a network to the engine’s program
format, loads it, and drives an execution stream, with no placement
planner in the path and no special entitlement for the operations the
compiler accepts. This route makes the engine a target a developer can
address on purpose rather than a scheduling hint. It is not a supported
or App-Store-safe path; see the status note in the front matter. Part II
covers it in full. 
 
 
 The stack from a graph to the silicon is a fixed set of layers, and the
direct route enters one level below Core ML at the runtime, as
 table   1.1 gives layer by layer. 
 
 
 Table 1.1: The software and firmware stack from a compute graph to the
silicon, with the role of each
layer. 
 
 
 
 
 
 Layer 
 
 
 
 Role 
 
 
 
 
 
 
 Core ML, the GPU graph framework, the direct runtime route 
 
 
 
 three
independent front ends 
 
 
 
 
 Espresso and the runtime 
 
 
 
 the universal compile, load,
and execution-stream layer 
 
 
 
 
 the engine framework and its daemon 
 
 
 
 program lifecycle, brokered over
cross-process messaging 
 
 
 
 
 the kernel driver 
 
 
 
 the coprocessor endpoint, mailbox
transport, signed program load 
 
 
 
 
 the firmware 
 
 
 
 the engine’s own real-time operating system, the dispatch
loop, the data-movement and power control 
 
 
 
 
 the silicon 
 
 
 
 the multiply array, the on-chip memory,
and the address-translation unit 
 
 
 
 
 
 The compile path requires the modern intermediate language, which the
compiler accepts only from the A13 and M1 generation up. The pre-A13
parts have no path through this toolchain, which is why the M1 is the
practical floor for addressing the engine directly. 
 
 
 
 1.2 One fact that explains the
machine 

 
 The products are fp16 while the accumulator is wide, of fp32 class, and
that property accounts for most of what the engine does. The datapath
multiplies in fp16 end to end: fp16 inputs, fp16 weights, fp16 outputs.
The frontend accepts fp32, int32, and bf16 type annotations, but the
backend does not implement them. The datapath reconstructs compressed
weights to fp16 before they reach the multiplier. 
 
 
 The running sum is not fp16. Input tiles round to fp16 on the way in,
the output port rounds to fp16 on the way out, and the accumulation
between those two points is held in a wide accumulator. Representable
sums thus come back near exact. A reduction of sixteen thousand ones is
bit exact, where a naive fp16 running sum would stall near two thousand
once the partial total exceeds the spacing of its own increments. A
cancellation probe settles the question: a sum of a large value, its
negation, and one, taken near sixteen thousand, returns the one intact,
which a fp16 running sum would have swallowed. The sum is physically
wider than fp16. 
 
 
 The wide accumulator is what suits the engine to vision, audio, and
encoders. Those workloads are convolutions, matrix multiplies, and
normalizations whose partial sums stay in range and whose results are
representable, so the accumulator holds their precision. The same
arithmetic explains where a transformer decoder loses precision in fp16.
The loss comes from the per-product fp16 rounding of the inputs and
weights under heavy cancellation, in the down-projection in particular,
not from the accumulator. The accumulator is wide enough; the inputs to
it are already quantized. A cancellation-heavy step has no fp16-safe
form on the engine and needs a wider anchor on the CPU or the GPU. 
 
 
 The fp16 datapath also accounts for the power efficiency. A narrow
multiply and a fixed-function pipeline move and compute far fewer bits
per result than a general-purpose vector unit. 
 
 
 
 1.3 Two core counts 

 
 The engine reports two different core counts, and only one is the
throughput unit. The advertised 16-core figure is the count Apple
markets, 16 on the M1, exposed at runtime as the device property for the
number of engine cores. The architectural figure is the core count the
compiler tiles work across and the cost model scales by, read from the
hardware-abstraction-layer offset 0x238 , which is 4 on the M1.
The core count is 4 on the M1 base part, 8 on the M1 Pro and Max, and 16
on the M5. Each core emits up to 4 output channels per cycle in the
default fp16 path. The M1 thus reaches about 16 output-channel
multiply-accumulates per cycle in fp16, and int8 doubles the lanes to
reach about 32, consistent with the overhead-isolated compute slope near
12 fp16 TFLOP/s. 
 
 
 
 1.4 Where it leads 

 
 On compute-bound work the engine is faster than the GPU outright. A 3x3
convolution at 256 channels runs about 3.8 times faster than the same
work on the GPU and about 9 times more energy efficient, and batched
matrix multiply is more efficient at every batch size, as
 table   1.2 records for both workloads. 
 
 
 Table 1.2: Engine versus GPU speed and efficiency on the convolution and
batched matrix multiply workloads. 
 
 
 
 
 
 workload 
 
 
 
 engine vs GPU speed 
 
 
 
 engine vs GPU efficiency 
 
 
 
 
 
 
 3x3 convolution (256 channels) 
 
 
 
 3.8x faster 
 
 
 
 9x more efficient 
 
 
 
 
 batched matrix multiply 
 
 
 
 faster below N of 2048 
 
 
 
 more
efficient at every batch size 
 
 
 
 
 
 The case where the GPU leads is real but limited: it holds for
bandwidth-bound autoregressive decode, where the work is moving weights
rather than computing on them. The measured envelope on the M1 fixes the
scale. The overhead-isolated compute slope reaches near P ≈ 12 P\approx 12 
fp16 TFLOP/s against a DRAM bandwidth of B ≈ 85 B\approx 85 GB/s, at about
 0.5 0.5 pJ per FLOP sustained, near 0.37 0.37 at the compute optimum. The
roofline ridge point, the arithmetic intensity above which a kernel is
compute-bound rather than bandwidth-bound, is at
 I ∗ = P / B ≈ 141 I^{*}=P/B\approx 141 FLOP per byte. A hard 2 MB on-chip
working-set threshold is the primary design limit: a kernel whose live
tiles exceed it stalls on off-chip streaming rather than running on the
multiplier. Newer chips scale the core count and the clock, but the form
of the roofline and the fp16 datapath apply across the family. 
 
 
 
 1.5 Reference: the M1 envelope 

 
 Table   1.3 collects the M1 envelope figures, the two
distinct core counts, and the family core-count span. 
 
 
 Table 1.3: The M1 envelope figures, the two distinct core counts, and the
family core-count span. 
 
 
 
 Quantity 
 Symbol 
 M1/H13 value 
 
 
 
 Compute roof 
 P P 
 12 fp16 TFLOP/s 
 
 DRAM bandwidth roof 
 B B 
 85 GB/s 
 
 Energy per FLOP 
 
 0.5 pJ sustained, 0.37 pJ optimum 
 
 Roofline ridge point 
 I ∗ I^{*} 
 141 FLOP/byte 
 
 On-chip working-set threshold 
 
 2 MB 
 
 fp16 maximum finite magnitude 
 
 65504 
 
 Advertised 16-core figure, M1 
 
 16 
 
 Core count, M1 (HAL 0x238 ) 
 
 4 
 
 Core count, M1 to M5 
 
 4 to 16 
 
 Output channels per cycle per core, fp16 
 
 4 
 
 
 
 
 
 
 

## Chapter 20 — 20 datapath/MAC geometry

ltx_tag_chapter">Chapter 20 Datapath and MAC geometry 

 
 
 SUMMARY 
 The multiply-accumulate array is four cores on the M1, each with an
eight-deep accumulator file, reading every geometry constant from a
per-chip hardware-abstraction table. The lane width emits eight output
channels per cycle in the int8 fast path and four in the default fp16
path, and output channels are the dimension that splits across cores and
across accumulator passes. Each core reduces through a radix-4 tree of
fp16-rounded tiles into one wide running accumulator of fp32 class,
rounding to fp16 only at the output port. The firmware has no
convolution, Winograd, or systolic code: it holds the real-time kernel
and the tile, kernel, and output direct-memory-access plumbing, and
nothing else. 
 
 
 
 The array is a set of cores, accumulators, and lanes whose dimensions
are constants in the compiler and in a per-chip hardware-abstraction
table. The compiler supplies it by re-basing direct-memory-access
engines per tile. Table   20.1 gives those dimensions and the
roofline that follows from them, with each constant’s
hardware-abstraction-table offset and the scope over which it holds. 
 
 
 20.1 Geometry constants 

 
 Table 20.1: The multiply-accumulate array geometry constants, with
hardware-abstraction-table offset, M1 value, and the scope over which
each holds. 
 
 
 
 quantity 
 table offset 
 M1 value 
 scope 
 
 
 
 core count 
 0x238 
 4 
 per die variant 
 
 accumulator budget per core 
 0x0c 
 8 
 all
chips 
 
 accumulator-split granule 
 0x230 
 64 
 all chips 
 
 performance cycle divisor 
 0x228 
 64 
 A12
and later 
 
 output channels per cycle, fp16 
 accessor table 
 4 
 architectural 
 
 output channels per cycle, int8 
 accessor table 
 8 
 architectural 
 
 patch-width floor, log2 
 0x400 
 4 
 M1 
 
 patch-width cap, log2 
 0x410 
 9 
 M1 
 
 working-set cap 
 0x1b8 
 2 MB 
 M1 
 
 
 
 
 The compiler’s performance model reads the array geometry from these
fields in the per-chip hardware-abstraction table. The die, not the
generation, keys the core count. The decoded four-core figure on the M1
counts physical compute sets, which the per-core power-rail step
confirms below. Apple’s published per-chip figure, the 16-core count the
I/O registry also reports, is a different quantity
 [AppleANE] . The M1 has four cores; the M5
generation has sixteen; small reference variants have one. The
accumulator budget of eight, uniform across every chip, is the depth of
the accumulator file per core in work units. An operation fits
single-buffered when its accumulator demand is at most eight, and
double-buffered when twice its demand is at most eight, so
double-buffering holds up to a demand of four. 
 
 
 
 20.2 Output channels per cycle and the lane
width 

 
 Two accessors of the performance model set the lane width, listed in
 table   20.2 with what each returns and the input that
selects the value. 
 
 
 Table 20.2: The two lane-width accessors of the performance model, with
what each returns and the input that selects the
value. 
 
 
 
 
 
 accessor 
 
 
 
 returns 
 
 
 
 selected by 
 
 
 
 
 
 
 GetNumOutputChannelsPerCycle 
 
 
 
 8 (int8 fast path), 4 (fp16
default), 2 or 1 (narrow modes) 
 
 
 
 data type and mode 
 
 
 
 
 GetNumOutputChannelsPerAccumulator 
 
 
 
 8 / 4 / 2
/ 1 (table below) 
 
 
 
 source-patch size 
 
 
 
 
 
 The second accessor selects among four per-accumulator channel counts by
source-patch size, which table   20.3 maps to the
hardware-abstraction-table offset that holds each value. 
 
 
 Table 20.3: Output channels per physical accumulator slot, the
hardware-abstraction-table offset holding each value, and the
source-patch size that selects
it. 
 
 
 
 HAL offset 
 output channels per accumulator 
 selected when 
 
 
 
 0x3a8 
 8 
 tiny-source mode (small-source-mode field reads
2) 
 
 0x3b0 
 4 
 small-source mode
(small-source-mode field reads 1) 
 
 0x3b8 
 2 
 default, format 3 / fp16-packed 
 
 0x3c0 
 1 
 default, non-format-3 and not
half-work-unit 
 
 
 
 
 The four values are not packed into one accessor argument: each is its
own field in the hardware-abstraction table at offsets 0x3a8 ,
 0x3b0 , 0x3b8 , and 0x3c0 , and
 GetNumOutputChannelsPerAccumulator returns the one the
operation’s source-patch mode selects. The values are uniform across
every chip in the set, so the multiplexing law is architectural, not
per-die. The source-patch mode is set by
 ComputeSmallSourceMode , which classifies an operation as
default, small, or tiny from the output tensor dimensions against the
kernel: tiny mode requires a source of at least 2 that fits the field at
 0x338 , which is 4 on the M1. 
 
 
 The lane width is the column dimension of the systolic tile.
 GetNumOutputChannelsPerCycle returns eight in the int8 fast
path and four in the default fp16 path, degrading to two or one for
narrow modes. One core streams an input patch and produces up to eight
output channels per cycle in double-int8 mode and four output channels
per cycle in fp16. GetNumOutputChannelsPerAccumulator sets how
many output channels time-share one physical accumulator slot. A tiny
input patch underuses the array spatially, so the compiler packs eight
output channels onto one accumulator to keep the multipliers busy. A
large patch lets each output channel keep its own accumulator. 
 
 
 
 20.3 Radix-4 reduction and wide
accumulator 

 
 The reduction that supplies one accumulator runs in two stages. The
first stage groups input lanes into tiles of four, each rounded to fp16.
Those fp16-rounded tiles supply one wide running accumulator of fp32
class, and the result rounds to fp16 only at the output port. 
 
 
 The fan-in of four is measured, not inferred from the table. A reduction
of [+B, -B, +1] triples, repeated sixteen times so that
the true sum is sixteen, returns sixteen survivors below a partial
magnitude of 4096 and saturates to exactly four survivors for every
 B at or above 4096. The saturation count of four is the radix-4
tile signature: once a tile holds a partial at or above 4096, the unit
increments sharing that tile fall below half of the fp16 spacing and
vanish, and the three-element triple period beats against the four-lane
tile to leave four unaffected lanes. The threshold is at 4096 because
that is where the fp16 spacing first reaches four. The result is
layout-independent: the [+B, -B, +1] and
 [+B, +1, -B] orderings return byte-identical values, so
the hardware reduction order is a fixed lattice over lane index and not
the source order. 
 
 
 The cross-tile accumulator is wider than fp16. A reduction of one value
of 4096 followed by 1024 ones returns 5116, between the naive-fp16
result 4096 and the exact 5120, and sixteen unit increments all survive
next to a partial of 8192 where a fp16 accumulator would drop most of
them. The radix-4 first stage is consistent with the eight-work-unit
accumulator file, since four input lanes plus margin fit the per-core
budget. 
 
 
 
 20.4 Output-channel-group tiling 

 
 The compiler tiles output channels into output-channel groups sized to
the accumulator file. ComputeMaxOcgSize derives the group size
from the accumulator budget, the kernel-element count, and a per-format
byte cap. 
 
 
 

 
 
 OCG = min ⁡ ( floor ​ _ ​ pow2 ​ ( 8 k W ​ k H ​ k D ) , byte ​ _ ​ cap ) , \mathrm{OCG}=\min\!\left(\mathrm{floor\_pow2}\!\left(\frac{8}{k_{W}\,k_{H}\,k_{D}}\right),\;\mathrm{byte\_cap}\right), 
 
 
 
 
 where the byte cap is 32, 16, or 8 bytes per kernel element depending on
the weight format, read from the hardware-abstraction table at offset
 0x388 , 0x390 , or 0x398 . In compiler terms,
 ComputeMaxOcgSize reads the accumulator budget at field
 0x0c , divides it by the kernel-element count, rounds down to a
power of two, and clamps to the per-format byte cap, as
 listing   32 gives. 
 
 
 List of listings 32 How the compiler computes the output-channel-group size for one pass from the accumulator budget, kernel-element count, and per-format byte cap. 
 
 
 # ComputeMaxOcgSize: output-channel-group size for one pass 
 
 
 acc_per_oc = GetNumOutputChannelsPerAccumulator(mode) # 1, 2, 4, or 8 
 
 
 budget = floor_pow2( HAL[ 0x0c ] / (kW * kH * kD) ) # HAL[0x0c] = 8 accumulators 
 
 
 byte_cap = HAL[ocg_cap_offset( format )] / (kW * kH * kD) # 0x388/0x390/0x398 = 32/16/8 B/elem 
 
 
 OCG = min ( ComputeMaxOcg(budget, acc_per_oc), byte_cap ) 
 
 
 
 A 1-by-1 convolution has a kernel-element count of one, so it admits a
large group. A 3-by-3 convolution has a kernel-element count of nine, so
its group is roughly nine times smaller and it needs more passes over
the input. The compiler relieves that pressure by selecting Winograd for
dense 3-by-3 stride-1 convolutions, since the transform cuts the
effective kernel-element count. 
 
 
 Once the output-channel count exceeds what one pass holds, the array
re-streams the input for a second pass. The number of passes is 
 
 
 

 
 
 OCG ​ passes = ⌈ C o ​ u ​ t OCG ⌉ . \mathrm{OCG\ passes}=\left\lceil\frac{C_{out}}{\mathrm{OCG}}\right\rceil. 
 
 
 
 
 For a 1-by-1 fp16 convolution at a 32-by-32 spatial size, the per-layer
slope shows a distinct super-linear jump in cost between an
output-channel count of 192 and 256: a step from 20 microseconds to 61
microseconds per layer, a roughly threefold cost step for a 1.8-fold
increase in arithmetic. That step is the pass count incrementing from
one to two as the group cap is reached. A 3-by-3 convolution reaches the
same threshold at fewer output channels per pass, matching the nine-fold
accumulator pressure. 
 
 
 
 20.5 Winograd selection gate 

 
 The eligibility gate is CanUseWinogradMode , a fixed conjunction
of conditions that all must hold, each given in
 table   20.4 with its meaning. 
 
 
 Table 20.4: The conditions of the Winograd eligibility gate, each of which
must hold for the mode to be
considered. 
 
 
 
 
 
 condition 
 
 
 
 meaning 
 
 
 
 
 
 
 HAL[0x680] bit 0 set 
 
 
 
 the per-chip Winograd-enable bit,
present on the M1 
 
 
 
 
 kernel underlying type not 5, not 2, not unity 
 
 
 
 the
format is Winograd-eligible and the weights are not 1-by-1 or
identity 
 
 
 
 
 tensor format not 12 
 
 
 
 the input format class is eligible 
 
 
 
 
 one kernel axis equals 3 
 
 
 
 the transformed axis is fixed
at 3, so 3-by-3 only 
 
 
 
 
 the orthogonal kernel axis is below 6 
 
 
 
 the input-tile width of the
larger tile is 6 
 
 
 
 
 no third (depth) kernel extent 
 
 
 
 two-dimensional
convolution 
 
 
 
 
 unit stride 
 
 
 
 input and output extents are consistent with stride 1 
 
 
 
 
 OCG x kH x kW x kD x 2 clears the work
threshold 
 
 
 
 enough work to amortize the transform 
 
 
 
 
 
 The axis-equals-3 plus orthogonal-axis-below-6 pair pins the supported
tile set to two forms: F ⁡ ( 2 × 2 , 3 × 3 ) F(2\times 2,3\times 3) , with an output
tile of 2 and an input tile of 4, and F ⁡ ( 4 × 4 , 3 × 3 ) F(4\times 4,3\times 3) ,
with an output tile of 4 and an input tile of 6. The work threshold on
the term OCG × k H × k W × k D × 2 \mathrm{OCG}\times k_{H}\times k_{W}\times k_{D}\times 2 is
precision-dependent: it is 32 for work-unit modes 1 and 2, 8 for a
non-float kernel, and 16 for a float kernel. The higher float threshold
is the compiler’s guard against the precision cost of the
 F ⁡ ( 4 × 4 , 3 × 3 ) F(4\times 4,3\times 3) transform, since the float convolution
must clear a larger work bar before the transform is taken. There is no
accumulator widening tied to Winograd: the precision safety is the
eligibility and threshold gating, not a wider accumulator. 
 
 
 Eligibility is not selection. Even when the gate passes, Winograd is
taken only when it beats both direct convolution and the
accumulator-double-buffering path, decided by a cost-model comparison
that reads the same accumulator and lane-width accessors. Winograd is
rejected when the convolution uses unicast, when the weight is sparse
(sparse weights keep their own datapath and skip zeros), or when
double-buffering the accumulator file already saturates the array. The
transform matrices themselves are not in the compiler: the compiler sets
a single winograd_mode config field, and the input, filter,
and output transforms run inside the engine datapath. The textbook
 F ⁡ ( 2 × 2 , 3 × 3 ) F(2\times 2,3\times 3) and F ⁡ ( 4 × 4 , 3 × 3 ) F(4\times 4,3\times 3) forms
describe the behavior, but the coefficients are resident in hardware and
not recoverable from the program. 
 
 
 
 20.6 Four-core granule 

 
 Output channels are the dimension the compiler splits across cores.
 ZinMirNECoreAssignment builds a strided round-robin map: core
 k k owns output channels { k , k + N , k + 2 ​ N , … } \{k,k+N,k+2N,\ldots\} for a core
count N N . On the M1 with four cores, channel c c is on core 
 
 
 

 
 
 core ⁡ ( c ) = c mod 4 . \mathrm{core}(c)=c\bmod 4. 
 
 
 
 
 The active-core count is shape-driven, not user-selectable. The compiler
sets it from the output-channel count and the group size, rounds it up
to the next power of two, and writes it into the task descriptor.
 GetNumNeededNEsNextPow2 sets the count, which
 listing   33 gives alongside the channel-to-core map and the
pass count. 
 
 
 List of listings 33 The strided round-robin channel-to-core map alongside the pass count and active-core count, both driven by the output-channel count and the group size. 
 
 
 # ZinMirNECoreAssignment: strided round-robin channel-to-core map (M1: num_nes = 4) 
 
 
 def core(c, num_nes): 
 
 
 return c % num_nes # channel c -> core c mod 4 on the M1 
 
 
 # OCG passes and active-core count, both driven by C_out and the OCG size 
 
 
 def ocg_passes(c_out, ocg): 
 
 
 return ceil(c_out / ocg) # input re-streamed once per pass 
 
 
 def cores_needed(c_out, ocg, num_nes): # num_nes = HAL[0x238] = 4 on the M1 
 
 
 return min (num_nes, next_pow2(ceil(c_out / ocg))) 
 
 
 
 Table   20.5 reports the measured throughput as the
active-core count rises from one to four, showing near-linear integer
scaling of the single-core rate. 
 
 
 Table 20.5: Measured throughput as the active-core count rises from one to
four. 
 
 
 
 output channels 
 cores lit 
 throughput,
GMAC/s 
 ratio to one core 
 
 
 
 1 
 1 
 3.8 
 1.00 
 
 2 
 2 
 7.6 
 2.00 
 
 3 
 3 
 11.4 
 3.00 
 
 4 
 4 
 15.4 
 4.05 
 
 
 
 
 Driving a single 1-by-1 convolution at each output-channel count below
the core count, in a dispatch loop pinned at a fixed rate by
per-dispatch overhead, the sustained throughput rises in exact integer
multiples of the single-core rate. Each added core does one more output
channel’s worth of multiply-accumulates in the same wall time. The power
rail confirms the count independently: the engine draws a step of about
10 milliwatts per added core over an always-on floor of about 800
milliwatts, matching the firmware’s one always-on base domain plus four
independently power-gated compute sets, one per core. 
 
 
 A live capture of the compiler during a real M1 compile pins the
geometry it costs against, which table   20.6 records
with the active-engine count and the candidate split geometries it
speculates. 
 
 
 Table 20.6: Costed-geometry constants captured live during an M1 compile,
with the active-engine count and the candidate split
geometries. 
 
 
 
 quantity 
 live M1 value 
 
 
 
 clusters costed 
 1 
 
 active engines costed
( GetTotalNumberOfActiveNEs ) 
 8 
 
 candidate split geometries speculated 
 1, 4, and 16 engines 
 
 kernel-memory budget 
 64 units 
 
 fixed per-layer overhead 
 44 cycles 
 
 
 
 
 The 8 active engines the compiler costs against differ from the 16 cores
the I/O registry reports for the M1: the costed geometry is 8 active
engines on 1 cluster, a model-internal figure rather than the registry
core count or the four physical compute sets that the power rail
confirms above. The model also holds a 64-unit kernel-memory budget that
weight residency must fit under, and a 44-cycle fixed per-layer overhead
that is added to every layer’s execute cycles. 
 
 
 The full datapath reads top to bottom from the output-channel groups
down through the four cores to each core’s accumulator and its radix-4
reduction, as figure   20.1 draws it. 
 
 
 Figure 20.1: The multiply-accumulate datapath, with output-channel groups tiled across four cores, each core holding a wide accumulator fed by a radix-4 reduction tree. 
 
 
 
 20.7 Roofline from the geometry 

 
 Peak fp16 throughput is the product of the core count, lane width, and
clock. Writing the lane width as output channels per cycle, the peak
rate of multiply-accumulate operations is 
 
 
 

 
 
 P MAC = cores × lanes × f , P_{\mathrm{MAC}}=\mathrm{cores}\times\mathrm{lanes}\times f, 
 
 
 
 
 and the floating-point rate is twice that, since one multiply-accumulate
is two floating-point operations. On the M1 the best fp16 mode is four
cores times four output channels per cycle, and the int8 fast path
doubles the lane width to eight. The measured all-four-cores-saturated
rate for a large 1-by-1 convolution is about 3.48 trillion
multiply-accumulates per second, about 7 fp16 TFLOP/s at the engine
output: above the 4.8 fp16 TFLOP/s large-matmul saturating ceiling of
chapter 9 , because this convolution stays under the
2 MB working-set threshold and remains compute-bound, and below the
overhead-subtracted roofline anchor of 12 fp16 TFLOP/s. The
full-saturation power at that rate is about 4.7 watts, which is on the
convolution power anchor and within 0.3 watts of the 4.4 watt
large-matrix-multiply anchor, so the rail readings are calibrated. 
 
 
 The frontend does not reach that doubled lane. The int8 compile flag
quantizes the weights and leaves the multiply-accumulate in fp16, so it
halves the streamed weight bytes and never emits the eight-channel int8
compute path. The flag thus changes weight bandwidth, not compute rate.
A 3-by-3 convolution at 256 input and output channels and a square
matmul both run within a few percent of fp16. The int8 path reaches
about 1.5 times faster only where the weight is large enough to stream
from main memory, near a 4096-by-4096 weight at a batch of 256 or more. 
 
 
 The working-set cap closes the roofline at the memory edge. The largest
single operand that stays on chip is 2 MB. Past that, the operand is
tiled and streamed from main memory, which adds traffic and moves the
workload onto the bandwidth side of the roofline. 
 
 
 
 20.8 Task descriptor that holds the
geometry 

 
 The compiler does not address the array directly: it fills a
per-partition task descriptor, a flat register image organized into
seven register groups, then serializes each group into the address-value
pairs the firmware writes. On the M1 the descriptor is the version-10
layout, one of fourteen versioned descriptor structs the compiler
builds, selected by chip family. Table   20.7 lists
the seven register groups of that layout, each with its register count,
address base, and contents. 
 
 
 Table 20.7: The seven register groups of the version-10 task descriptor,
each with its register count, address base, and
contents. 
 
 
 
 
 
 group 
 
 
 
 register count 
 
 
 
 address base 
 
 
 
 contents 
 
 
 
 
 
 
 kernel and common 
 
 
 
 34 
 
 
 
 0x5500 
 
 
 
 kernel-DMA enable, format,
stride, common config, task type, output transpose, network id 
 
 
 
 
 dimensions 
 
 
 
 19 
 
 
 
 none 
 
 
 
 input and output width, height,
depth, channels, group count, broadcast, transpose, interleave,
output-channel-group size 
 
 
 
 
 tile DMA 
 
 
 
 69 
 
 
 
 0x4d00 
 
 
 
 the three tile-DMA engines: enable,
cache hints, base-address halves, row, channel, depth, group strides,
format, wrap 
 
 
 
 
 elementwise, planar engine, padding 
 
 
 
 30 
 
 
 
 0x4100 
 
 
 
 elementwise and planar-engine config, padding mode,
planar-engine index 
 
 
 
 
 L2 and texture 
 
 
 
 14 
 
 
 
 0x4500 
 
 
 
 L2 source and result config,
texture mode, source dimensions 
 
 
 
 
 kernel format and op mode 
 
 
 
 11 
 
 
 
 0x4900 
 
 
 
 op
mode, kernel alignment, sparse and palette flags, padding constant, bias
and post-scale enables 
 
 
 
 
 L2 result 
 
 
 
 21 
 
 
 
 0x5100 
 
 
 
 L2-result base, strides, wrap, result
format 
 
 
 
 
 
 The dimension group encodes the per-axis caps directly in its field
widths. Input width, height, and depth are 15-bit fields masked
 0x7fff , while the channel fields are 17-bit, masked
 0x1ffff , so a channel axis reaches 131071 where a spatial axis
stops at 32767. The output-channel-group size is a 3-bit field, and the
active-core count is the ActiveNE field, a 3-bit value that
records how many cores the task runs on, set from the shape by
 GetNumNeededNEsNextPow2 . 
 
 
 A fused convolution folds its per-channel affine and its activation into
four separate kernel-coefficient streams, each a distinct sub-buffer
with its own base offset and a relocation slot the loader patches at
load. Table   20.8 names the four streams, each with the
relocation register the loader patches and the role it holds. 
 
 
 Table 20.8: The four kernel-coefficient streams a fused convolution emits,
each with the relocation register the loader patches and the role it
holds. 
 
 
 
 
 
 stream 
 
 
 
 relocation register 
 
 
 
 role 
 
 
 
 
 
 
 bias 
 
 
 
 0x1554 
 
 
 
 the per-channel additive offset 
 
 
 
 
 post-scale 
 
 
 
 0x1558 
 
 
 
 the per-channel output
multiply, where a dequantize scale folds 
 
 
 
 
 palette lookup 
 
 
 
 0x155c 
 
 
 
 the palettized-weight lookup table 
 
 
 
 
 activation lookup 
 
 
 
 0x1560 
 
 
 
 the 33-segment
piecewise-linear activation table 
 
 
 
 
 
 A convolution with batch normalization and a following activation thus
does not become four operations: the scale and bias fold into the
post-scale and bias streams, the activation runs as the
activation-lookup stream, and one fused operation streams all four
coefficient banks alongside its weights. 
 
 
 
 
 

## Chapter 24 (targets & profiles — per-die core sequence)

ltx_tag_chapter">Chapter 24 HAL and capability gates 

 
 
 SUMMARY 
 The compiler is one binary that builds any chip in the line from a
per-chip data table, the hardware abstraction layer, read at compile
time. The table holds scalar fields indexed by byte offset for the
numeric limits and a dense capability-byte region at offsets
 0x48f through 0x8cc , each byte read as
 hal[offset] & 1 to gate one operation or format.
Operation legality is declared on the operation as a
 MinimumFamily<N> trait: native only when
the target family index is N or greater, and decomposed below
the floor, with no compute operation floored above A15. A capability in
the table attests support at the layer that reads it and does not prove
the operation runs: three-dimensional convolution has its kernel-depth
attestation at 0x70 and fails backend lowering on every device
mask. 
 
 
 
 The compiler that targets the Apple Neural Engine is one binary that
builds any chip in the line on demand. What separates one target from
the next is a per-chip data table, read at compile time, that records
every size limit and every per-operation switch for that silicon. 
 
 
 24.1 HAL property table 

 
 The hardware-abstraction-layer table is the compiler’s profile of a
target, one packed structure that holds both the numeric limits and the
feature gates for a chip. Table   24.1 gives
representative scalar fields of the hardware-abstraction table, each
with its offset, meaning, M1 value, and the generation at which it
changes. 
 
 
 Table 24.1: Representative scalar fields of the hardware-abstraction table;
the full decoded register map is in Appendix
 C . 
 
 
 
 
 
 Offset 
 
 
 
 Field 
 
 
 
 Meaning 
 
 
 
 M1 (H13) 
 
 
 
 Changes at 
 
 
 
 
 
 
 0x1b8 
 
 
 
 max_operand_bytes 
 
 
 
 on-chip SRAM working set 
 
 
 
 2 MB 
 
 
 
 constant across the line (1 MB on M9) 
 
 
 
 
 0x1c0 
 
 
 
 dram_alignment 
 
 
 
 DMA width
granule in bytes 
 
 
 
 16 
 
 
 
 constant (1 only on the small profiles) 
 
 
 
 
 0x1c8 
 
 
 
 l2_bank_align 
 
 
 
 DMA bank-conflict modulo 
 
 
 
 64 
 
 
 
 constant 
 
 
 
 
 0x1f0 
 
 
 
 L2-resident buffer threshold 
 
 
 
 dedicated-buffer trip 
 
 
 
 0 
 
 
 
 32768 at A15, 262144 at A16 
 
 
 
 
 0x200 
 
 
 
 dense kernel-memory cap 
 
 
 
 non-streamed weight ceiling 
 
 
 
 64 KB 
 
 
 
 the fold-path budget 
 
 
 
 
 0x210 
 
 
 
 streamed kernel-memory cap 
 
 
 
 streamed
weight ceiling 
 
 
 
 16 MB 
 
 
 
 the stream-path budget 
 
 
 
 
 0x218 
 
 
 
 instruction or segment alignment 
 
 
 
 record packing
granule 
 
 
 
 256 
 
 
 
 16 at A14 
 
 
 
 
 0x228 
 
 
 
 ne_perf_cycle_divisor 
 
 
 
 cost-model per-cycle divisor 
 
 
 
 64 
 
 
 
 32 on H11, 16 on M9 
 
 
 
 
 0x238 
 
 
 
 num_nes 
 
 
 
 NE-core count 
 
 
 
 4 (base) 
 
 
 
 die-keyed: 4, 8, 16, 32, 64 
 
 
 
 
 0x288 
 
 
 
 extended dual-kernel-memory mode 
 
 
 
 16
MB versus 64 KB select 
 
 
 
 0 
 
 
 
 0 on all 28 targets 
 
 
 
 
 0x70 
 
 
 
 max_large_conv_kernel_dim_z 
 
 
 
 3D-conv
kernel depth 
 
 
 
 16 
 
 
 
 capability attested at A13 (1 below) 
 
 
 
 
 0x138 
 
 
 
 max_tensor_width 
 
 
 
 maximum
tensor width 
 
 
 
 16384 
 
 
 
 65536 at A16 
 
 
 
 
 0x158 
 
 
 
 max_tensor_depth 
 
 
 
 maximum tensor depth 
 
 
 
 16384 
 
 
 
 1 below A13, 65536 at A16 
 
 
 
 
 0x3f0 
 
 
 
 reduction-via-transpose extent 
 
 
 
 reduction route threshold 
 
 
 
 192 
 
 
 
 384 at A15 
 
 
 
 
 0x400 
 
 
 
 pe_min_patch_width_log2 
 
 
 
 the
 2 4 = 16 2^{4}=16 -pixel tiling floor 
 
 
 
 4 
 
 
 
 constant M1 and M5 
 
 
 
 
 0x580 
 
 
 
 cost-model policy name 
 
 
 
 roofline
anchor string 
 
 
 
 Simple 
 
 
 
 None on older and small
profiles 
 
 
 
 
 0x668 
 
 
 
 interchange-format map size 
 
 
 
 count of accepted image
formats 
 
 
 
 3 
 
 
 
 13 at A14, 16 at A15, 14 at A16 
 
 
 
 
 
 The hardware abstraction layer is a single packed structure the compiler
constructs for its target, holding two kinds of entry. The first is a
block of scalar fields, indexed by byte offset, that record numeric
limits: maximum kernel sizes, maximum tensor dimensions per axis, the
on-chip working-set size, data-movement alignment granule, and
cost-model curve. The second is a dense region of single-byte boolean
flags, the capability bytes, each gating one operation or one format on
or off for the target. A family of constructors, one per architecture,
builds the structure per target inside the compiler. The scalar region
runs from offset 0x18 to roughly 0x348 as plain data,
with non-scalar members such as the format map and the cost-model curve
extending past it. The capability-byte region occupies offsets
 0x48f through 0x8cc and holds on the order of 165
single-byte flags, of which 24 have recovered field names and the rest
are enumerated by offset and classified by the family that enables them.
The compiler reads a scalar as a value at its offset and a capability
byte as hal[offset] & 1 , so every limit and every gate
is one indexed read into this one table. The same structure holds the
cost model: a policy-name string at 0x580 ,
frequency-to-efficiency curve at 0x7a8 , and per-cycle divisor
at 0x228 , which the roofline of chapter
 18 reads from this table
rather than from a separate file. 
 
 
 Listing   47 gives a partial C view of the structure, with
each selected scalar field and the capability-byte region at its
recovered offset. 
 
 
 List of listings 47 A partial C view of the per-target hardware-abstraction structure, with selected scalar fields and the capability-byte region at their recovered offsets. 
 
 
 /* ZinIrHalParameters, selected fields at their byte offsets (M1/H13 values) */ 
 
 
 struct ZinIrHalParameters { 
 
 
 /* ... */ 
 
 
 uint64_t max_large_conv_kernel_dim_z ; /* 0x70: 3D-conv kernel depth = 16 */ 
 
 
 /* ... */ 
 
 
 uint64_t max_tensor_width ; /* 0x138: max tensor width = 16384 */ 
 
 
 /* ... */ 
 
 
 uint64_t max_operand_bytes ; /* 0x1b8: SRAM working set = 2 MB */ 
 
 
 uint64_t dram_alignment ; /* 0x1c0: DMA width granule = 16 */ 
 
 
 uint64_t l2_bank_align ; /* 0x1c8: DMA/L2 bank count = 64 */ 
 
 
 /* ... */ 
 
 
 uint64_t num_nes ; /* 0x238: NE-core count = 4 */ 
 
 
 /* ... */ 
 
 
 uint8_t cap_bytes [ 0x8cd - 0x48f ]; /* 0x48f..0x8cc: per-op capability flags */ 
 
 
 }; 
 
 
 
 The capability bytes are read one at a time as
 hal[offset] & 1 , for example the texture engine at
 0x81d and the kernel-streaming master at 0x48f . 
 
 
 
 24.2 Operation gate 

 
 Operation legality is declared not in the HAL table but on the operation
itself, as a trait the compiler attaches to every backend operation. The
trait is a minimum-family index: the operation
 MinimumFamily<N> is natively legal only
inside a compilation whose family index is N or greater, and
below that floor the compiler decomposes it into legal operations. The
family index orders the generations: A11Legacy is 0,
 A12 is 1, A13 is 2, A14 is 3, A15 is
4, and so on, with the M1 at A13 and the M5 at A17 . 
 
 
 The check the compiler runs on each backend operation is the trait floor
against the target family index, which listing   48 gives
as the native-or-decompose decision. 
 
 
 List of listings 48 The minimum-family gate, where an operation is emitted natively when the target family meets its floor and decomposed otherwise. 
 
 
 # mlir::OpTrait::anec::MinimumFamily<N>: native iff target family >= N 
 
 
 def op_is_native(op, target_family): 
 
 
 return target_family >= op.minimum_family # e.g. softmax N=2 (A13), sin N=4 (A15) 
 
 
 def lower_op(op, target_family): 
 
 
 if op_is_native(op, target_family): 
 
 
 emit_native(op) # one anec op 
 
 
 else : 
 
 
 decompose(op) # rewrite into ops legal below the floor 
 
 
 
 The M1 has family index two and the M5 has family index six, so an
operation with floor four, such as sin, is native on the M5 and
decomposed on the M1. 
 
 
 The floors fall into a small number of tiers. The base tier, family 0,
holds the operations every engine runs: convolution, matrix multiply,
pooling, the elementwise and activation set, reshape, transpose, and
concat. At A13 come softmax, the normalizations, the reductions, fused
attention, and the square-root and error functions. A14 brings the
texture-engine samplers, crop-resize, and resample; A15 brings native
sin and cos. No compute operation floors above A15, so the newest
generations add core count and clock rather than new operations. 
 
 
 The two gate mechanisms work together. A capability byte read as
 hal[offset] & 1 decides a route inside a single
operation, for example whether the texture engine at byte 0x81d 
is present, which on the M1 reads 0 and forces resize to a
decomposition. The minimum-family trait decides whether the operation is
native at all. When either gate is closed, the compiler either emits a
decomposition into legal operations or rejects the operation with a
message naming the architecture, depending on whether a legal
decomposition exists. 
 
 
 Table   24.2 gives the minimum-family floors a developer
reaches, each with the families it is native on and its representative
operations. 
 
 
 Table 24.2: The minimum-family floors a developer reaches, with the
families each is native on and representative
operations. 
 
 
 
 
 
 Floor 
 
 
 
 Native on 
 
 
 
 Representative operations 
 
 
 
 
 
 
 F0 
 
 
 
 all families 
 
 
 
 convolution, matmul, pooling, elementwise, reshape,
transpose, concat 
 
 
 
 
 F2 (A13+) 
 
 
 
 A13 onward 
 
 
 
 softmax, layer and instance and
batch norm, reductions, attention, erf, sqrt 
 
 
 
 
 F3 (A14+) 
 
 
 
 A14 onward 
 
 
 
 crop-resize, resample 
 
 
 
 
 F4 (A15+) 
 
 
 
 A15 onward 
 
 
 
 sin, cos, global argmin and
argmax 
 
 
 
 
 
 Because the floor is an attribute of the operation and the limits are a
table keyed to the chip, the per-chip difference is data, not code. The
compiler text that rewrites an operation is identical across the family,
and the chip selects a different limit, gate, or decomposition strategy
from the table beneath it. 
 
 
 
 24.3 Capability-byte gates across the
line 

 
 A capability byte is a single-byte switch in that table that turns one
operation or feature on or off for a target. Table   24.3 
gives the named capability bytes, each with its gate and its value
across the M1 and the later generations. 
 
 
 Table 24.3: The named capability
bytes. 
 
 
 
 
 
 Byte 
 
 
 
 Gate 
 
 
 
 M1 (H13) 
 
 
 
 A14 
 
 
 
 A15 
 
 
 
 A16 
 
 
 
 A18 
 
 
 
 
 
 
 0x48f 
 
 
 
 kernel-streaming master, the 64 KB to 16 MB select 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x494 
 
 
 
 square-after-reduction fusion 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x4a9 
 
 
 
 dropout and random 
 
 
 
 0 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x4f2 
 
 
 
 global argmin and argmax 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x529 
 
 
 
 per-format kernel-stride enable, the palette stream 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x52d 
 
 
 
 fp8 E4M3 kernel format 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 1 
 
 
 
 
 0x563 
 
 
 
 FIFO-mode direct memory access 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 1 
 
 
 
 
 0x815 
 
 
 
 softmax, native 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x816 
 
 
 
 instance normalization, native 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x81a 
 
 
 
 local-response normalization, native 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 0x81d 
 
 
 
 texture engine 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 
 
 The texture engine at byte 0x81d is the largest M1 functional
gap: it reads 0 on the M1 and 1 from A14 onward. It gates resize,
crop-resize, resample, affine transform, hardware gather, and symmetric
padding all together, so each of those routes through a software
decomposition on the M1. The fp8 byte 0x52d is set on the A18
generation alone of the 28 targets, so the M5, an A17 part, does not
have it. The streaming master at byte 0x48f and the
palette-stream byte 0x529 both read 1 on the M1, which is why
the int4 palette and the sparse form stream on the M1, while int8 and
blockwise fold, a mechanism chapter 25 
develops. The compiler builds the table for a target by calling that
target’s constructor, so a single host recovers the table for every chip
in the line whether or not it is the chip that is running. 
 
 
 
 24.4 Per-family scalar matrix 

 
 The scalar parameters across the generation anchors show the same
pattern: a value holds for a span of generations and then steps once, as
 Table   24.4 gives across the generation anchors. 
 
 
 Table 24.4: The scalar parameters at the generation
anchors. 
 
 
 
 Field (offset) 
 M1 (H13) 
 A14 
 A15 
 A16 (M4) 
 A17 (M5) 
 
 
 
 num_nes ( 0x238 ) 
 4 
 4 
 4 
 4 
 16 
 
 max_operand_bytes ( 0x1b8 ) 
 2 MB 
 2
MB 
 2 MB 
 2 MB 
 2 MB 
 
 max_tensor_width ( 0x138 ) 
 16384 
 16384 
 16384 
 65536 
 65536 
 
 max_tensor_depth ( 0x158 ) 
 16384 
 16384 
 16384 
 65536 
 65536 
 
 max_large_conv_kernel_dim_z ( 0x70 ) 
 16 
 16 
 16 
 16 
 16 
 
 L2-resident threshold ( 0x1f0 ) 
 0 
 0 
 32768 
 262144 
 262144 
 
 instruction alignment ( 0x218 ) 
 256 
 16 
 16 
 16 
 16 
 
 reduction-transpose extent ( 0x3f0 ) 
 192 
 192 
 384 
 384 
 384 
 
 interchange-format count ( 0x668 ) 
 3 
 13 
 16 
 14 
 14 
 
 
 
 
 The base-name M5 reads num_nes of 16 because the column is the
16-core Pro-class profile, while the base A17 profile has 4. The per-die
sequence runs 4 for the base name, 8 for the g suffix, 16 for
 s and the legacy 16-core profile, 32 for c , and 64 for
the d Ultra-class die. 
 
 
 
 24.5 Kernel-memory split 

 
 The streaming master byte does more than gate the compressed-weight
stream: it selects which of two kernel-memory caps a layer’s weights are
sized against. The legalization check is two lines of logic, reading a
streamable flag and the master byte to pick the offset of the cap, then
comparing the demand against it, as listing   49 gives. 
 
 
 List of listings 49 The kernel-memory split, where a streamable weight under the streaming master is sized against the 16 MB cap and a dense weight against the 64 KB cap. 
 
 
 # ExceedKmemSizeLimit: split-legalize a layer's weights when they exceed the cap 
 
 
 def exceeds_kmem(hal, demand, is_streamable): 
 
 
 cap = hal[ 0x210 ] if (is_streamable and hal[ 0x48f ]) else hal[ 0x200 ] 
 
 
 return cap < demand # 0x200 = 64 KB dense, 0x210 = 16 MB streamed 
 
 
 
 An ordinary non-streamed weight over 64 KB, or any weight over 16 MB, is
thus split into multiple sub-layers on the M1, which raises the dispatch
count and the compile time. A streamed compressed weight is sized
against the 16 MB cap and has far more weight per layer. This is the
weight path; it does not bound the activations, which stay within the
maximum-tensor-dimension caps, so a layer with a tiny weight and a large
activation is bounded by tiling cost in the partition passes rather than
by this discrete limit. 
 
 
 
 24.6 Dead and family-gated
fields 

 
 Not every per-target value in the table is a live gate. A byte-granular
re-diff of all 28 target blobs leaves zero undecoded scalar fields, but
several offsets that vary by family are populated by the per-chip
builder and never read back through the table pointer, so their value is
a write-only mirror. Five scalar offsets are dead as table fields in
this fashion: the global element cap at 0x18 , kernel-depth
constant at 0x80 , legacy tiling granule at 0x260 ,
offset at 0x320 , and die-class flag at 0x29c . Each
varies meaningfully by family, but the value a reader consumes is read
off a different object that shares the byte displacement, a
tensor-dimensions, compiler-parameters, or memory-pools structure, not
the table. The distinguishing test is whether the base register at the
access holds the table pointer, since the same displacement aliases
dozens of other by-reference structures, so a raw displacement match
inside a table-typed function is not proof of a table read. 
 
 
 The one offset that looks dead on the M1 but is not is the FIFO-mode
byte at 0x563 : it reads 0 on the M1 and is read through the
table pointer under a branch that is taken only when the byte is set,
which happens on the A18 generation. A per-family value pattern alone
does not establish a live gate; only a traced reader off the table base
does. 
 
 
 
 24.7 Naming the remaining capability
flags 

 
 The capability bytes and the scalar limits are both fields of one
struct, ZinIrHalParameters , the per-family blob the compiler
builds for its target. The struct has no per-field getter method, so the
compiler reads a field through an inlined ldrb or ldr 
off the table pointer at a fixed offset, which is why a first pass
recovers offsets and values but not names. The names survive in one
place only. The compiler retains full mangled C++ symbols, and a reader
function whose signature has ZinIrHalParameters const& reads
each field, so the reader’s name labels the field it reads. A read is
attributed to the table only when the load’s base register is the
function’s ZinIrHalParameters const& argument, since the same
byte displacement aliases dozens of other by-reference structures. 
 
 
 Cross-referencing the unnamed offsets against these reader functions
names 95 more of them, of which roughly 30 resolve to a precise
individual meaning with the base register verified against the table
argument, the recovered names Table   24.5 attributes each
to its reader function. 
 
 
 Table 24.5: Precise capability-flag names recovered this round, each
attributed to its reader
function. 
 
 
 
 
 
 Offset 
 
 
 
 Field 
 
 
 
 Reader function 
 
 
 
 
 
 
 0x4a8 
 
 
 
 PE work-unit-shape supported 
 
 
 
 PERasterization::ComputeWUShape 
 
 
 
 
 0x4ac 
 
 
 
 small-source-mode compression supported 
 
 
 
 ZinANELayer::AllowCompressionBasedOnSmallSourceMode 
 
 
 
 
 0x4b0 
 
 
 
 non-power-of-2 work-unit width supported 
 
 
 
 NERasterization::CanUseNonPowerOf2WUs 
 
 
 
 
 0x4f0 
 
 
 
 preferred kernel layout format 
 
 
 
 ZinIrKernel::GetPreferredKernelLayoutFormat 
 
 
 
 
 0x500 
 
 
 
 transpose and multicast configuration 
 
 
 
 ZinNELayer::FindValidMirInfoForTransposeCore 
 
 
 
 
 0x520 
 
 
 
 secure-mode cache-hint DSID gate 
 
 
 
 GetDSIDFromPriorityHalAndSecureMode 
 
 
 
 
 0x52c 
 
 
 
 tensor-format support flag, pairs with the named
 0x52d fp8 byte 
 
 
 
 ZinLayerValidationUtils::ValidateFormat 
 
 
 
 
 0x54c 
 
 
 
 cache-prefetch kernel-task-interval
limit 
 
 
 
 ZinValidateTd<17>::ValidateCachePrefetchKernelTaskInterval 
 
 
 
 
 0x5a8 
 
 
 
 cache-hint DSID value 
 
 
 
 GetDSIDFromPriorityHalAndSecureMode 
 
 
 
 
 0x708 
 
 
 
 reflective-padding maximum extent 
 
 
 
 ZinValidateTd<20>::ValidateReflectivePaddingMode 
 
 
 
 
 0x748 
 
 
 
 gather and texture-engine descriptor pointer 
 
 
 
 ZinGatherLayer::CreateTELayer 
 
 
 
 
 0x8b4 
 
 
 
 tile-height-errata threshold 
 
 
 
 ZinTileHeightErrata::Workaround 
 
 
 
 
 0x8bc 
 
 
 
 chaining enabled 
 
 
 
 ZinIrRegAllocUtil::IsChainable 
 
 
 
 
 0x8e0 
 
 
 
 kernel-caching enabled 
 
 
 
 ZinIrTdValidationUtil::ValidateKernelCaching<N> 
 
 
 
 
 
 The remaining 95-minus-30 additions are class-named: the reader
identifies the subsystem the field gates without the exact semantics.
Examples are the per-axis DMA range bounds read by
 ZinValidateTd<N>::CheckInRangeDmaAccess 
and the texture-engine plane-equation coefficients in the 0x820 
to 0x8f8 block gated by the named 0x81d texture-engine
byte on A14 and later. Two candidates were rejected as table fields
despite matching a displacement inside a table-typed function:
 0xcf8 loads off an adrp -formed read-only constant
rather than the table, and 0x678 loads off a nested object two
pointers deep. The same base-register test that found the five dead
fields above also rules these out. 
 
 
 With this round the silicon-capability subset of the packed bitfield,
the part the compiler reads to gate a feature per family, is fully
named. The struct is 0x938 bytes, and the few entries inside it
that are not capability flags are the cost-model coefficient block at
offsets 0x580 through 0x7f0 . This block holds the
frequency-to-efficiency curve, rate indices, performance multiplier that
the roofline of chapter 18 
reads, and about two soft fp64 coefficients. These are all performance
coefficients rather than legality caps. A small number of capability
fields are also true holdouts, read only off aliased bases. The offsets
past 0x938 hold no table: an earlier reading that located an
A12 operation-emulation catalog at 0xa30 through 0xe84 
was a read into the adjacent zeroed memory beyond the struct, not a real
field. 
 
 
 
 24.8 Attested is not reachable 

 
 A capability recorded in the HAL table attests support at the layer that
reads the table. It does not by itself prove that the operation lowers
to a task descriptor and runs on the silicon. These are distinct layers,
and a capability present at the first can fail at the second. 
 
 
 The case that fixes the rule is three-dimensional convolution. The HAL
scalar at offset 0x70 records a 3D-conv kernel depth of 16 on
the M1, attesting that the kernel geometry is permitted, and the
compiler frontend recognizes the operation. It still fails backend
lowering on every device mask, returning the message that it is not
supported on any backend. The capability is in the table and the
operation does not run. 
 
 
 The gap appears in the other direction as well, where a checker accepts
an operation the code generator rejects. On the M1 the top-k, sort, and
dynamic-slice validators are all callable and all three are refused at
code generation. A bit in the table, a frontend that recognizes an
operation, or a validator that passes are each a claim about one layer;
only a compile-and-run on the target confirms the operation at the layer
that executes it. This is why the reachable surface of chapter
 4 is smaller than the surface the table
advertises, and why each native entry there was compiled and run on the
M1 rather than inferred from a capability byte. 
 
 
 
 
 <span class="ltx_tag 

## Chapter 33 — 33 telemetry & hardware counters (Table 33.3)

ltx_tag_chapter">Chapter 33 Telemetry and hardware counters 

 
 
 SUMMARY 
 The engine has a hardware performance-counter block of twenty-four
per-task-descriptor counters, master enable at
 ANEProgramCreateArgs+0x6c , and free-running firmware timestamp
at MMIO 0x2_6b17_8000 . The block geometry and the timestamp
are readable, but the per-task-descriptor counter values are not,
because one kernel gate blocks them on the unentitled path. Forcing the
stats mask non-zero turns a successful load into a rejected one, since
the compiled program has no stats-descriptor section for the kernel to
size. What remains readable is the whole-engine telemetry outside that
gate: DRAM read and write bytes, engine energy in millijoules, and
clock-state residency. 
 
 
 
 33.1 Counter block geometry 

 
 Table   33.1 gives the per-task-descriptor counter
groups, the number of counters in each, and a representative counter
name. 
 
 
 Table 33.1: The per-task-descriptor counter groups, with the count in each
and a representative counter
name. 
 
 
 
 
 
 Group 
 
 
 
 Counters in group 
 
 
 
 Representative counter 
 
 
 
 
 
 
 Neural engine cycles 
 
 
 
 6 
 
 
 
 kANE_NE_COMPUTE_CYCLES ,
 kANE_NE_INPUT_STALL_CYCLES 
 
 
 
 
 L2 (on-chip 2 MB) cycles 
 
 
 
 4 
 
 
 
 kANE_L2_NOMINAL_CYCLES ,
 kANE_L2_READ_STALL_CYCLES 
 
 
 
 
 L2 processing-element cycles 
 
 
 
 3 
 
 
 
 kANE_L2PE_COMPUTE_CYCLES 
 
 
 
 
 Precision compute cycles 
 
 
 
 2 
 
 
 
 kANE_FP16_CYCLES , kANE_INT8_CYCLES 
 
 
 
 
 Kernel-manager stall 
 
 
 
 1 
 
 
 
 kANE_KM_STALL_CYCLES 
 
 
 
 
 Data-movement bytes 
 
 
 
 7 
 
 
 
 kANE_DMA_READ_BYTES , kANE_L2_TO_NE_DATA 
 
 
 
 
 Per-descriptor energy 
 
 
 
 1 
 
 
 
 kANE_DPE_ENERGY 
 
 
 
 
 
 The per-task-descriptor counter namespace is twenty-four named counters,
every one of them per task descriptor, grouped by engine block.
 Table   33.2 gives the complete namespace, recovered
from the counter-name accessor and grouped by engine block. 
 
 
 Table 33.2: The complete twenty-four-counter per-task-descriptor namespace,
recovered from the counter-name accessor, grouped by engine
block. 
 
 
 
 
 
 Group 
 
 
 
 Counters 
 
 
 
 
 
 
 Neural engine cycles 
 
 
 
 kANE_NE_NOMINAL_CYCLES ,
 kANE_NE_COMPUTE_CYCLES , kANE_NE_THROTTLE_CYCLES ,
 kANE_NE_INPUT_STALL_CYCLES ,
 kANE_NE_OUTPUT_STALL_CYCLES ,
 kANE_NE_KERNEL_STALL_CYCLES 
 
 
 
 
 On-chip 2 MB memory cycles 
 
 
 
 kANE_L2_NOMINAL_CYCLES , kANE_L2_THROTTLE_CYCLES ,
 kANE_L2_READ_STALL_CYCLES ,
 kANE_L2_WRITE_STALL_CYCLES 
 
 
 
 
 L2 processing-element cycles 
 
 
 
 kANE_L2PE_COMPUTE_CYCLES ,
 kANE_L2PE_INPUT_STALL_CYCLES ,
 kANE_L2PE_OUTPUT_STALL_CYCLES 
 
 
 
 
 Precision compute cycles 
 
 
 
 kANE_FP16_CYCLES ,
 kANE_INT8_CYCLES 
 
 
 
 
 Kernel-manager stall 
 
 
 
 kANE_KM_STALL_CYCLES 
 
 
 
 
 Data-movement bytes 
 
 
 
 kANE_DMA_READ_BYTES ,
 kANE_DMA_READWRITE_BYTES , kANE_AF_TO_KM_DATA ,
 kANE_AF_TO_L2_DATA , kANE_L2_TO_AF_DATA ,
 kANE_L2_TO_NE_DATA , kANE_NE_TO_L2_DATA 
 
 
 
 
 Per-descriptor energy 
 
 
 
 kANE_DPE_ENERGY 
 
 
 
 
 
 The byte counters track data movement along the activation-function to
kernel-manager to L2 to neural-engine path, and one per-descriptor
counter estimates energy from the digital-power estimator. With this set
a host can attribute, per scheduling unit, whether a task descriptor is
compute-bound, input-stalled, output-blocked, or throttled, directly in
hardware counters. The master enable is a single field in the
program-create argument struct. It is the per-task-descriptor stats mask
at ANEProgramCreateArgs+0x6c , a u32 that is after the
quality-of-service field and the packed boolean flags and before the
memory-pool identifier, located in the argument fields of
 Listing   70 . 
 
 
 List of listings 70 The program-create argument fields, with the per-task-descriptor stats-mask master enable at offset +0x6c. 
 
 
 ANEProgramCreateArgs ( offsets ): 
 
 
 + 0x18. . + 0x57 : two SHA256 - class hashes ( model hash + key ) 
 
 
 + 0x5c ( u32 ) : count ( number of procedures ) 
 
 
 + 0x64 ( u32 ) : qos = 21 ( 0x15 ) 
 
 
 + 0x68 ( u32 ) : packed bool flags = 0x10 
 
 
 + 0x6c ( u32 ) : statsMask <- the per - TD counter master enable 
 
 
 + 0x70 ( u32 ) : memoryPoolID = 0 
 
 
 + 0x80 : program name "main_main__Op0_AneInference" 
 
 
 
 The driver remaps a client-facing mask to a driver mask before it
reaches this field. The remap keeps only the low nibble: a mask of
 0xffffffff translates to a driver mask of 0x0 , that
is, no collection, and 0xf is the only fully-enabled
translation. 
 
 
 

 
 
 driverMask ⁡ ( m ) = { remap ⁡ ( m mod 16 ) m < 16 0 m ≥ 16 \mathrm{driverMask}(m)=\begin{cases}\mathrm{remap}(m\bmod 16)&m<16\\
0&m\geq 16\end{cases} 
 
 
 
 
 When the mask is non-zero the firmware writes each task descriptor’s
counter block into a shared stats buffer in DRAM. The host decoder is
built against the sCAneStatsData ABI version 0x0201 ,
distinct from the on-wire header magic 0x0101 the firmware
writes into the buffer (chapter 29). The buffer’s required size is the
sum of the stats header, event descriptors, and per-event records. The
host decodes it through a parser that walks a Group to Layer to
task-descriptor hierarchy, where the leaf task-descriptor node holds the
counter block. 
 
 
 
 33.2 Free-running timestamp 

 
 A monotonic firmware timestamp underlies the whole telemetry surface.
The firmware reads it from a single free-running memory-mapped counter
through the one-line helper of Listing   71 , then stamps each
trace-event record from that read. 
 
 
 List of listings 71 The firmware helper that reads the free-running engine timebase counter. 
 
 
 /* free-running engine timebase counter, read by the firmware helper @0x30988 */ 
 
 
 #define ANE_TIMEBASE_COUNTER 0x26b178000 ULL /* MMIO 0x2_6b17_8000 */ 
 
 
 static inline uint64_t ane_read_timebase ( void ) { 
 
 
 return *( volatile uint64_t *) ANE_TIMEBASE_COUNTER ; /* ldr x0, [x8] ; ret */ 
 
 
 } 
 
 
 
 Each firmware trace-event record has a timeStamp field
alongside its task-descriptor identifier, network identifier, program
identifier, process identifier, and task-queue, as
 Listing   72 shows. 
 
 
 List of listings 72 The fields of each firmware trace-event record. 
 
 
 [ANE_TM_EVENT_START]: tid, nid, progId, procId, currTQ, timeStamp 
 
 
 [ANE_TM_EVENT_FINISH]: tid, nid, progId, procId, currTQ, timeStamp 
 
 
 [ANE_EVENT_CONTEXT_SWITCH_IN]: tid, nid, prevTQ, progId, procId, currTQ, timeStamp 
 
 
 
 The host-visible clock residency runs in 24 MHz ticks, one tick every
41.67 ns, read out of the system-on-chip state-residency channels. The
timestamp is monotonic and survives a power-gate, since the firmware
re-anchors it from the same free-running source rather than resetting it
across a clock-state transition. It is the basis for the per-dispatch
wall-clock intervals that the signpost stream exposes, and it is
readable with no entitlement beyond root. 
 
 
 
 33.3 What the host can read and what it
cannot 

 
 The block geometry and the timestamp are observable; the counter values
are not. The split follows the stats mask: the timestamp and the
whole-engine channels do not route through it, and the
per-task-descriptor counters do, as Listing   73 
contrasts. 
 
 
 List of listings 73 The readable timestamp and whole-engine channels contrasted with the blocked per-task-descriptor counter path. 
 
 
 /* READABLE: no stats mask in the path */ 
 
 
 uint64_t t = ane_read_timebase (); /* free-running firmware timestamp */ 
 
 
 int64_t rd = ioreport_delta ( "AMC Stats|Perf Counters|ANE0 RD" ); /* DRAM read bytes */ 
 
 
 int64_t mj = ioreport_delta ( "Energy Model|-|ANE0" ); /* engine energy, mJ */ 
 
 
 /* BLOCKED: gated by the per-task-descriptor stats mask */ 
 
 
 args . statsMask = 0xf ; /* master enable, ANEProgramCreateArgs+0x6c */ 
 
 
 create = ANE_ProgramCreate (& args ); /* create -> 1 */ 
 
 
 load = ANE_ProgramLoad ( create ); /* load -> 0: initStatsBufferSection bails */ 
 
 
 perf = read_perf_iosurface (); /* every byte 0: per-run output buffer is null */ 
 
 
 
 The values are blocked because the master enable never takes effect on
the host path. On the unentitled runtime path the runtime sets the stats
mask to 0 below the model layer, so firmware collection is
never armed and the per-run output buffer comes back null. Forcing the
mask non-zero through an in-process hook does not help: the
program-create call then reaches the kernel routine of
 Listing   74 , which looks up the program’s
stats-descriptor section by name, reads its size field, and bails on a
zero size. The aned daemon is what zeroes the mask: it sets
 statsMask=0 for a coreAnalyticsClientType of
 ThirdPartyAppUsingANE , so the mask is cleared by client type,
and the host-side null check is the string
 perfStatsIOSurface is NULL! . 
 
 
 List of listings 74 The kernel routine that bails when the stats-descriptor section size is zero, failing the create call. 
 
 
 initStatsBufferSection(ANEProgramCreateArgsOutput*, task*): 
 
 
 ldr w8, [x8, #0x28] ; size of the stats-descriptor section 
 
 
 str w8, [x28] 
 
 
 cbz w8, bail ; size 0 => return 0 (create fails) 
 
 
 ... ; non-zero => kalloc + map the stats buffer 
 
 
 
 The compiled program has no stats-descriptor section, so the size is
always zero and the kernel returns failure. Forcing a non-zero mask thus
turns a successful load into a rejected one
( create -> 1; load -> 0 ), and no
host-side primitive synthesizes the missing section. One kernel gate
thus blocks both the per-task-descriptor counters and the per-run output
buffer: each depends on a stats-descriptor section that only an internal
profiling-compile emits. 
 
 
 What remains readable is the whole-engine telemetry outside that gate,
the channels of Table   33.3 with their format,
unit, and what each reads out. 
 
 
 Table 33.3: The whole-engine telemetry channels readable on the unentitled
path, with their format, unit, and what each reads
out. 
 
 
 
 
 
 Channel 
 
 
 
 Format 
 
 
 
 Unit 
 
 
 
 Reads out 
 
 
 
 
 
 
 AMC Stats \| Perf Counters \| ANE0 RD 
 
 
 
 fmt=1 delta integer 
 
 
 
 B 
 
 
 
 DRAM read bytes 
 
 
 
 
 AMC Stats \| Perf Counters \| ANE0 WR 
 
 
 
 fmt=1 delta integer 
 
 
 
 B 
 
 
 
 DRAM write bytes 
 
 
 
 
 AMC Stats \| Perf Counters \| ANE0 DCS RD 
 
 
 
 fmt=1 delta integer 
 
 
 
 B 
 
 
 
 DRAM read bytes via the
compression-subsystem path 
 
 
 
 
 AMC Stats \| Perf Counters \| ANE0 DCS WR 
 
 
 
 fmt=1 delta integer 
 
 
 
 B 
 
 
 
 DRAM write bytes via the
compression-subsystem path 
 
 
 
 
 Energy Model \| - \| ANE0 
 
 
 
 fmt=1 delta integer 
 
 
 
 mJ 
 
 
 
 engine energy 
 
 
 
 
 PMP \| AF BW \| ANE0 RD+WR 
 
 
 
 fmt=2 residency 
 
 
 
 events 
 
 
 
 aggregate read-plus-write bandwidth
events 
 
 
 
 
 SoC Stats \| Cluster Power States \| ANE0 
 
 
 
 fmt=2 residency 
 
 
 
 24Mticks 
 
 
 
 clock-state residency 
 
 
 
 
 SoC Stats \| Events \| SOC0_ANE_F1 ,
 SOC0_ANE_F2 
 
 
 
 fmt=2 residency 
 
 
 
 24Mticks 
 
 
 
 clock-domain
frequency-point residency 
 
 
 
 
 SoC Stats \| Events \| ANE0_ADCLK_TRIG ,
 ANE0_DITHR_TRIG 
 
 
 
 fmt=2 residency 
 
 
 
 24Mticks 
 
 
 
 adaptive-clock
and dither trigger ticks 
 
 
 
 
 Interrupt Statistics \| ane0 0 
 
 
 
 fmt=1 counters 
 
 
 
 counts, MATUs 
 
 
 
 first and second-level
interrupt-handler count and time 
 
 
 
 
 
 The memory-controller per-agent byte counters report DRAM read and write
bytes for the engine, both on the raw path and separately on the
compression-subsystem path, and the energy model reports engine energy
in millijoules. The system-on-chip state channels report clock
residency, frequency-point residency, and the adaptive-clock and dither
trigger counts, and the per-map fabric arbiter reports the engine’s
bandwidth and clock-floor votes. The interrupt statistics report the
host kernel’s cost of servicing engine completions, in counts and Mach
Absolute Time Units, split into first-level and second-level handlers
and isolated separately for the engine and its address-translation unit.
A storage coprocessor that an earlier reading mistook for the engine,
exposing vector-lane read and write counters, is unrelated to engine
telemetry; the bandwidth counter is the memory-controller ANE0 
channel and the power channel is the energy model. 
 
 
 The aggregate bandwidth channel resolves into per-channel histograms,
the fabric channel PMP0 / DCS BW / ANE L0 and L1 
carrying read and write distributions for the two DRAM read channels,
read as State-residency histograms rather than plain integers. The
 SoC Stats / Events channel also exposes the throttle-trigger
family ANE_THROTTLE_{SW,HW,PPT,DITHER,EXT}_TRIG and
 VDD_DRAM_VOLTAGE_CHANGE , per-trigger software, hardware,
peak-power, and dither throttle counts, all readable without
entitlement. 
 
 
 The per-dispatch op lifecycle is also readable as the timestamped
signpost stream of Listing   75 , captured on the engine
subsystem with no entitlement beyond root, which confirms the
three-request structure of a dispatch without exposing any counter
value. 
 
 
 List of listings 75 The client-side signpost intervals of one dispatch, with the three driver requests that correspond to the Cast, AneInference, and Cast program operations. 
 
 
 _ANEF_MODEL_EVALUATE one per host execute call 
 
 
 _ANEF_MODEL_EVAL 
 
 
 _ANEF_MODEL_EVAL_DRIVER_REQUEST request 1 of the dispatch (Cast) 
 
 
 _ANEF_MODEL_EVAL_DRIVER_REQUEST request 2 of the dispatch (AneInference) 
 
 
 _ANEF_MODEL_EVAL_DRIVER_REQUEST request 3 of the dispatch (Cast) 
 
 
 _ANEF_MODEL_EVAL_PERFCOUNTER_SAMPLE the per-descriptor counter sample is reported here when armed 
 
 
 _ANEF_MODEL_COMPILE _ANEF_MODEL_LOAD _ANEF_MODEL_UNLOAD 
 
 
 _ANEF_IOSURFACES_MAP _ANEF_INPUT_BUFFERS_READY _ANEF_ENQUEUE_OUTPUT_SET 
 
 
 
 Each interval has a Mach-time begin stamp, and the three driver requests
are the three program operations of a dispatch, one driver-to-firmware
request each. The firmware reports the blocked per-descriptor counter
sample on the evaluate interval only when the stats mask is armed, so
the signpost stream confirms the dispatch structure on live silicon
while the counter values stay behind the same gate. 
 
 
 
 33.4 Roofline and power figures from the readable
channels 

 
 The measured roofline elsewhere in this guide rests on the readable
whole-engine channels, not on the blocked per-descriptor counters.
Bandwidth comes from a delta on the memory-controller byte counters
across a real workload. A 96-layer matmul chain at batch 8192 moved 17.2
GB of reads and 16.9 GB of writes over 432 ms, which is between 79 and
90 GB/s, the engine’s share of the unified memory. A delta on the
energy-model millijoule channel over the same run gives about 0.48
pJ/FLOP and about 2.3 W under sustained compute. 
 
 
 The compute roof and the dispatch floor are wall-clock measurements,
timed against the firmware timestamp and the host clock rather than read
from a counter. The 2 MB working-set threshold is confirmed directly
from the byte counters. At batch 8192 the activation is exactly 2 MB,
the counters show 426 MB of DRAM moved per dispatch, arithmetic
intensity falls to 60 FLOP/byte, and throughput drops from 12 TFLOP/s to
about 4.8 TFLOP/s. The per-descriptor counters would attribute that drop
to specific stall classes, the input-stall and L2-read-stall cycles, but
the whole-engine byte and energy channels already locate the workload on
the bandwidth slope, which is what the roofline needs. 
 
 
 
 Part IX 
   
 
 Cross-Silicon Reference 
   
 
 34    Cross-silicon targets 
 
 
 The full target set and the rule mapping each M-series part to its H-series identity. 
 
 
 35    Per-family code generation 
 
 
 How one compiler binary builds every chip from a per-family data table. 
 
 
 36    Predicted upper tier 
 
 
 fp8 and the double-rate path the newest generations add. 
 
 
 
 
 
 

## Chapter 34 — 34 architecture strings

ltx_tag_chapter">Chapter 34 Cross-silicon targets 

 
 
 SUMMARY 
 The compiler builds 28 architecture targets, one per silicon profile,
under the fixed relation M ⁡ ( n ) → H ⁡ ( n + 12 ) M(n)\rightarrow H(n+12) . A suffix letter
selects the NE-core count, and the operation surface stops expanding at
A15, so the surface measured on the M5 is the surface for everything
above it. A device’s runtime architecture string is a separate
identifier from the compiler target name. A resolver-derived board-type
sequence maps every shipping chip onto its generation. 
 
 
 
 The compiler that builds for the Apple Neural Engine has 28 architecture
targets, one per silicon profile it knows how to construct. Each target
is a named hardware-abstraction-layer table the compiler builds by
calling one per-architecture constructor,
 ZinIrHal<T>::GetParams() , and calling
every constructor on a single host recovers the full set regardless of
which chip runs it. 
 
 
 34.1 Full set 

 
 Table   34.1 gives all 28 targets, each with its silicon class
and decoded NE-core count. 
 
 
 Table 34.1: The 28 compiler targets, each with its silicon class and
decoded NE-core count. 
 
 
 
 Target 
 Silicon and class 
 NE cores 
 
 
 
 H11 , H12 , M9 , T0 
 pre-A13 legacy 
 1 to 4 
 
 H13 
 A13, M1 base 
 4 
 
 H13g 
 M1 Pro, Max, Ultra 
 8 
 
 T1 
 A13 reference 
 4 
 
 H14 
 A14, M2 base 
 4 
 
 H14g 
 M2 Pro, Max 
 8 
 
 H14c 
 A14 Max-class 
 32 
 
 H15 
 A15, M3 base 
 4 
 
 H15g 
 M3 Pro, Max 
 8 
 
 H15c 
 A15 Max-class 
 32 
 
 H16 
 A16, M4 base 
 4 
 
 H16g 
 M4 Pro, Max 
 8 
 
 H16s 
 A16 Pro-class 
 16 
 
 H16c 
 A16 Max-class 
 32 
 
 H17 
 A17, M5 base 
 4 
 
 H17a 
 A17 variant 
 4 
 
 H17g 
 M5 Pro, Max 
 8 
 
 H17s 
 A17 Pro-class, the M5 
 16 
 
 H17c 
 A17 Max-class 
 32 
 
 H17d 
 A17 Ultra-class 
 64 
 
 H18 
 A18 base 
 4 
 
 M11 
 small embedded ANE 
 1 
 
 U1 , U2 , U3 
 reference, not silicon 
 4 
 
 
 
 
 The names fall into four groups: the H-architecture targets that stand
for shipping A-series and M-series silicon, the pre-A13 legacy targets,
a single small embedded profile, and three reference targets that are
not silicon at all. A suffix letter selects the NE-core count within a
generation, which the compiler decodes from the core-count field at
hardware-abstraction-layer offset 0x238 . The base name is 4
cores, the suffix g is 8, s is 16, c is 32,
and d is 64, while M9 and M11 are
single-core. H17s is thus the 16-core Pro-class part that is
the M5, and H17d is the 64-core Ultra-class die, the largest in
the table. These decoded num_nes values are the compiler’s
per-die core field, not Apple’s marketing Neural Engine count; on the
base M1 the decoded four stands against the published sixteen
 [AppleANE] . 
 
 
 The reference targets hold placeholder limits that no part has: a
maximum tensor depth of 1, a kernel-width limit of 1023, and no
interchange-format support. They are unconstrained validation profiles
the compiler builds for its own checking, not addressable silicon. The
small embedded profile M11 is addressable silicon. It is an
efficiency-class engine that has the A16-class feature flags but the
A13-class 16384-dimension limit, a single NE core, and the odd
kernel-width ceiling of 15 that is between the A13 value of 13 and the
A14 value of 16. 
 
 
 
 34.2 Capability tiers 

 
 Table   34.2 groups the targets into capability tiers, giving
each tier its dimension limit and the four gated capabilities that
separate the generations. 
 
 
 Table 34.2: The capability tier of each target, with the dimension limit
and the four gated capabilities that separate the
generations. 
 
 
 
 
 
 Tier 
 
 
 
 Targets 
 
 
 
 Max dimension 
 
 
 
 3D conv 
 
 
 
 Texture engine 
 
 
 
 sin , cos 
 
 
 
 Dropout 
 
 
 
 
 
 
 pre-A13 
 
 
 
 H11 , H12 , M9 , T0 
 
 
 
 16384,
depth 1 
 
 
 
 no 
 
 
 
 no 
 
 
 
 no 
 
 
 
 no 
 
 
 
 
 A13 
 
 
 
 H13 , H13g , T1 
 
 
 
 16384 
 
 
 
 yes 
 
 
 
 no 
 
 
 
 no 
 
 
 
 no 
 
 
 
 
 A14 
 
 
 
 H14 , H14g , H14c 
 
 
 
 16384 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 no 
 
 
 
 no 
 
 
 
 
 A15 
 
 
 
 H15 , H15g , H15c 
 
 
 
 16384 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 A16 
 
 
 
 H16 , H16g , H16s , H16c 
 
 
 
 65536 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 A17 
 
 
 
 H17 , H17a , H17g ,
 H17s , H17c , H17d 
 
 
 
 65536 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 A18 
 
 
 
 H18 
 
 
 
 65536 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 small 
 
 
 
 M11 
 
 
 
 16384 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 reference 
 
 
 
 U1 , U2 , U3 
 
 
 
 65535 placeholder 
 
 
 
 no 
 
 
 
 no 
 
 
 
 no 
 
 
 
 no 
 
 
 
 
 
 A17 and A18 add no operation over A16: identical dimension limits,
identical kernel-width and kernel-depth ceilings, the same texture
engine, same dropout and global-argmax flags, and same legal operation
set. They differ from A16 only in NE-core count, which scales throughput
rather than legality. The operation behavior measured on the M5, an H17
part, is thus the operation behavior of every target at or above A16,
since the decoded capability tables are identical; the cross-silicon
performance measurements of chapter
 12 are predicted to carry to the
unshipped generations on the same basis, with the per-chip rates
confirmed only on the two measured silicon points. 
 
 
 
 34.3 Silicon to target 

 
 The map from a shipping chip to its architecture is a resolver Apple
distributes that decompiles cleanly. The method
 aneArchitectureType on the private device-info class builds the
architecture string from a board-type value read from the platform
configuration store, switching on a strictly increasing board-type
sequence. The live anchor on an M1 Max reads board type 96, which
resolves to h13g with a 16-core count, matching the registry
exactly. Table   34.3 gives the resolver-derived map from
system-on-chip to runtime architecture and compiler target across the M1
through M5 generations. 
 
 
 Table 34.3: The resolver-derived map from system-on-chip to runtime
architecture and compiler target, M1 through
M5. 
 
 
 
 Chip 
 Product 
 Runtime arch 
 Compiler target 
 
 
 
 T8103 
 M1 base 
 h13 
 H13 
 
 T600x 
 M1 Pro, Max, Ultra 
 h13g 
 H13G 
 
 T8112 
 M2 base 
 h14 
 H14 
 
 T602x 
 M2 Pro, Max 
 h14g 
 H14G 
 
 T8122 
 M3 base 
 h15 
 H15 
 
 T603x 
 M3 Pro, Max 
 h15g 
 H15G 
 
 T8132 
 M4 base 
 h16 
 H16 
 
 T604x 
 M4 Pro, Max 
 h16g 
 H16G 
 
 T8142 
 M5 base 
 h17 
 H17 
 
 T605x 
 M5 Pro, Max 
 h17s 
 H17s 
 
 
 
 
 The map follows the fixed M ⁡ ( n ) → H ⁡ ( n + 12 ) M(n)\rightarrow H(n+12) relation of
chapter 12 . The sequence is anchored
at both ends, the live M1 Max at h13g and the measured M5 Pro
at h17s , and the intervening steps are corroborated
independently. A single shipping vision filter has exactly the five
tables H13 , H14 , H15 , H16 ,
 H17 , the five Mac engine generations. The board-type kext for
an absent chip cannot be read on a different host, since only the
running chip’s table is resident, so each middle step rests on the
anchored monotone sequence. 
 
 
 
 34.4 Runtime string and compiler
target 

 
 The architecture name a device reports at runtime is not the compiler
target name. The runtime string is the coarse form, h1N for a
base part and h1Ng for a Pro, Max, or Ultra part, the only two
variants the runtime emits on the desktop platform. The compiler target
is the finer set, the full H17 , H17s , H17c ,
 H17d , H17g family, of which the runtime collapses
several onto one string. A developer names the target by its compiler
form and treats the runtime string as a separate identifier. 
 
 
 The direct compile entry point accepts any of the 28 target names and
rejects an unknown name. The dispatch library, in contrast, falls back
silently when handed an unknown architecture, so a developer gates a
cross-target compile against the known-name set before dispatching it. 
 
 
 
 34.5 Interchange formats across the
set 

 
 Each target has a per-chip table of accepted image-input formats, the
interchange-format map at hardware-abstraction-layer offset
 0x658 , keyed by a four-byte ASCII format tag.
 Table   34.4 gives the accepted image-input format count by
generation tier, with the format set each tier adds. 
 
 
 Table 34.4: The accepted image-input format count by generation tier, with
the format set each tier adds. 
 
 
 
 
 
 Tier 
 
 
 
 Chips 
 
 
 
 Format count 
 
 
 
 Set 
 
 
 
 
 
 
 older, reference 
 
 
 
 H11 , H12 , M9 , T0 ,
 U1 , U2 , U3 
 
 
 
 0 
 
 
 
 none 
 
 
 
 
 A13, M1 
 
 
 
 H13 , H13g , T1 
 
 
 
 3 
 
 
 
 &BGA , &L0h , &L16 
 
 
 
 
 A14 
 
 
 
 H14 , H14g , H14c 
 
 
 
 13 
 
 
 
 A13 set,
RGBA-half, three compression variants 
 
 
 
 
 A15 and small 
 
 
 
 H15 , H15g ,
 H15c , M11 
 
 
 
 16 
 
 
 
 A14 set, YUV 4:2:0, luma-half 
 
 
 
 
 A16, A17, A18 
 
 
 
 H16 , H17 , H18 families 
 
 
 
 14 
 
 
 
 A15 set minus YUV 4:2:0 
 
 
 
 
 
 The tag is a one-byte compression-variant prefix on a three-byte base
pixel format. The compiler does not parse the prefix character by
character: it validates the whole four-byte tag against a 34-entry
allow-list, and the prefix’s meaning is the third byte of the format’s
packed-integer value, a packing-mode index on a uniform stride.
 Table   34.5 gives the compression-variant prefix on an
interchange tag and the packing-mode index it selects. 
 
 
 Table 34.5: The compression-variant prefix on an interchange tag and the
packing-mode index it selects. 
 
 
 
 Prefix 
 Mode index 
 Meaning 
 
 
 
 & 
 0 
 uncompressed, default raster surface 
 
 - 
 1 
 lossless compression, 32 by 32
macroblock 
 
 / 
 2 
 lossless compression, 16 by 16 macroblock 
 
 \| 
 3 
 lossless
compression, mode 3 
 
 * 
 0 
 compound prefix that sets the dynamic-channel flag 
 
 
 
 
 The packed integer that names each format is three bytes: a pixel class,
a base-format code, and the packing-mode index. The base-format codes
are BGRA8 ( BGA , code 0x11 ), RGBA-half ( RhA ,
code 0x13 ), 8-bit luma ( L0h , code 0x07 ),
16-bit luma ( L16 , code 0x08 ), and YUV 4:2:0
( 8f0 and 8v0 , code 0x09 ). A base format
routes to a vector of 20-byte plane descriptors, each a tuple of width
divisor, height divisor, element type, channel count, and depth. BGRA8
is thus one four-channel uint8 plane, and YUV 4:2:0 is a luma plane with
a half-resolution two-channel chroma plane. The binary string that reads
“Architecture only supports lossless compression” confirms that
 & is the uncompressed variant and that - , / ,
and | are the lossless-compressed packing families. 
 
 
 The A15 generation and the small embedded profile are the only targets
in the set that accept YUV 4:2:0 input, in both full-range
( 8f0 ) and video-range ( 8v0 ) form. The M5 and every
A16-and-later part keep luma-half but drop the two YUV 4:2:0 formats.
The full per-target format records, the wider 10-bit and packed YUV
family, and the plane-layout structures are appendix material. 
 
 
 
 
 

## Chapter 36 — 36 core-count sequence

ltx_tag_chapter">Chapter 36 Predicted upper tier 

 
 
 SUMMARY 
 Two datapaths are above the M5 in the compiler that no part measured
here can run: an fp8 weight and activation format, and a multi-die
collective communication layer. Both are present as decoded structure,
gated off on every family this guide reached, and stated as predicted,
not measured. The fp8 gate is the capability byte at offset
 0x52d , set on H18 alone; the collective-enable byte at offset
 0x48b reads zero on all 28 targets. 
 
 
 
 36.1 64-core ceiling 

 
 The largest die this guide measured is the 16-core H17s, and the line
ends at the 64-core H17d that no part here could run. The decode shows
that nothing extra is family-gated for the 64-core case beyond the count
itself, and the following is read from the compiler rather than measured
on a 64-core part. Core count is a runtime parameter, the
 ne_core_count value sourced from the hardware-abstraction
blob, not a hard-coded per-family constant. getDeviceInfo takes
that count as its second argument and buckets it against the thresholds
7, 10, 20, and 40, which straddle the four die sizes 8, 16, 32, and 64
held by the g , s , c , and d target
suffixes. Several device-information fields then scale linearly with the
count, and the top bucket reached on the A14-and-above branch stores the
800-unit peak. The compiler thus emits a 64-core-scaled cost model for
H17d purely from the count of 64, and the geometry is decoded while the
realized 64-core throughput stays an on-silicon measurement. 
 
 
 The two datapaths above the M5 are the fp8 weight format and the
multi-die collective layer, which table   36.1 gives field by
field, with each gate and its state on the M5. 
 
 
 Table 36.1: The decoded fields of the two fp8 formats and the collective
layer, with their gates and their state on the
M5. 
 
 
 
 
 
 field 
 
 
 
 E4M3 
 
 
 
 E5M2 
 
 
 
 collective layer 
 
 
 
 
 
 
 sign bits 
 
 
 
 1 
 
 
 
 1 
 
 
 
 not applicable 
 
 
 
 
 exponent bits 
 
 
 
 4 
 
 
 
 5 
 
 
 
 not applicable 
 
 
 
 
 mantissa bits 
 
 
 
 3 
 
 
 
 2 
 
 
 
 not applicable 
 
 
 
 
 exponent bias 
 
 
 
 7 
 
 
 
 15 
 
 
 
 not applicable 
 
 
 
 
 max finite magnitude 
 
 
 
 448 
 
 
 
 57344 
 
 
 
 not applicable 
 
 
 
 
 role 
 
 
 
 gated weight and activation 
 
 
 
 fp16 conversion 
 
 
 
 mesh reduce, gather, slice 
 
 
 
 
 family gate 
 
 
 
 0x52d set on H18 only 
 
 
 
 folds to fp16 broadly 
 
 
 
 0x48b zero on all 28 
 
 
 
 
 register encoding 
 
 
 
 present from A17 encoder 
 
 
 
 output
slot on modern encoders 
 
 
 
 every setter a stub 
 
 
 
 
 state on M5 
 
 
 
 off 
 
 
 
 conversion available 
 
 
 
 inert 
 
 
 
 
 
 
 36.2 fp8 datapath 

 
 The compiler has two eight-bit floating-point formats, and they are not
symmetric in role. They are in the internal ZinTensorFormat 
code-generation and direct-memory-access enumeration, not in the
serialization data-type enumeration that the operation attributes use.
The serialization enumeration runs codes 0 through 10 with fp16 at 3,
fp32 at 4, and int8 at 2, and has no fp8 codepoint at all; the fp8
formats are recovered from the byte-size map
 _ZinTensorFormatGetSizeInBytes . Table   36.2 gives
the fp8 codepoints in the internal tensor-format enumeration, with the
integer and half-precision neighbors that bound them. 
 
 
 Table 36.2: The fp8 codepoints in the internal tensor-format enumeration,
with the integer and half-precision neighbors that bound
them. 
 
 
 
 ZinTensorFormat code 
 Format 
 Bytes 
 
 
 
 1 
 int8 
 1 
 
 2 
 uint8 
 1 
 
 3 
 fp16 
 2 
 
 0xb (11) 
 fp32 
 4 
 
 0xc (12) 
 E4M3 
 1 
 
 0xd (13) 
 E5M2 
 1 
 
 0xe (14) 
 two-byte live-input format 
 2 
 
 0x10 (16) 
 int4 
 under 1 
 
 
 
 
 The compiler has the full set of fp8 variant types as C++ symbols,
 e4m3_t with 1273 references and e5m2_t with 176,
alongside the finite-and-NaN and unsigned-zero variant type classes. The
shipping format is the E4M3FN variant, proven by the ± 448 \pm 448 
saturation bound that
 ZinPadLayer::ValidateBackgroundPaddingValue enforces with the
string “in [%u, %u] for e4m3 format” and the NaN-only special
case in ZinE4M3Expand . 
 
 
 E4M3 is the gated weight and activation format. A value decodes from a
sign bit, four-bit exponent, and three-bit mantissa as 
 
 
 

 
 
 x = ( − 1 ) s ​  2 e − 7 ​ ( 1 + m 2 3 ) x=(-1)^{s}\,2^{e-7}\left(1+\frac{m}{2^{3}}\right) 
 
 
 
 
 for a normal value, with an exponent bias of 7 7 and a maximum finite
magnitude of 448 448 . The shipping variant is E4M3FN, the finite-and-NaN
form: it has no infinity, the all-ones exponent with a full mantissa
encodes NaN, and a value past ± 448 \pm 448 either maps to NaN or clamps
to the maximum normal. A one-bit mode held per direct-memory-access
source controls the overflow behavior, 0 0 for NaN and 1 1 for
saturate, so a narrowing cast picks the bit pattern 𝟶 ​ 𝚡 ​ 𝟽 ​ 𝚎 \mathtt{0x7e} 
for the saturated maximum or 𝟶 ​ 𝚡 ​ 𝟽 ​ 𝚏 \mathtt{0x7f} for NaN. The narrower
exponent and the ± 448 \pm 448 ceiling cap the representable range below
half precision. 
 
 
 E5M2 is a conversion format, not a gated weight format. It decodes as 
 
 
 

 
 
 x = ( − 1 ) s ​  2 e − 15 ​ ( 1 + m 2 2 ) x=(-1)^{s}\,2^{e-15}\left(1+\frac{m}{2^{2}}\right) 
 
 
 
 
 with five exponent bits, a two-bit mantissa, and the same exponent bias
of 15 15 as half precision. That shared exponent is why E5M2 is the
high byte of an fp16 value: the conversion to fp16 is a left shift of
eight bits, and the inverse is the top byte with round-to-nearest and an
infinity clamp. E5M2 folds to fp16 by a direct-memory-access conversion,
so it is broadly available wherever that conversion path exists, and the
upscaler layer accepts it as input. The fold asymmetry is exact in the
conversion functions. ZinE5M2ToF16 is a left shift of eight
bits, the literal high byte, and ZinF16ToE5M2 is the top byte
with round-to-nearest and an infinity clamp at 0x7c00 . E4M3 is
not so trivial. ZinE4M3Expand is a bit-surgery decode with sign
at bit 7, the four-bit exponent at bits 6 through 3, and the three-bit
mantissa at bits 2 through 0, handling the subnormal and NaN encodings.
 ZinF32ToE4M3 narrows and selects the overflow byte,
 0x7e for the saturated maximum and 0x7f for NaN. The
fold predicate IsFormatDMAConvertibleToFP16 returns
 (fmt < 0xe) & (0x2ff0 >> fmt) ,
and the mask 0x2ff0 includes code 13 and excludes code 12. E5M2
thus folds by direct-memory-access conversion and E4M3 cannot, which is
the binary-level reason E4M3 requires the native datapath that is gated. 
 
 
 The family gate is a single hardware-abstraction-layer capability byte
at offset 0x52d , the E4M3 direct-memory-access and
kernel-format capability. It is clear on the M1 generation, clear on the
M5 generation, and clear on the intermediate families, and it reads set
on the H18 family alone of the twenty-eight compiler targets. The master
per-format direct-memory-access validity function
 CheckValidDMAFormat takes the four capability bytes
 HAL[0x52c] , HAL[0x52d] ,
 HAL[0x52e] , and HAL[0x685] . It validates fp32
against 0x52c , E4M3 against 0x52d , E5M2 against
 0x52e , and the two-byte live formats against 0x685 ,
with every code below 0xb always valid. Three
operation-semantics sites re-check the byte and abort with “E4M3 is not
supported on this architecture”: the dequantize validator at line
129078, the quantize validator at line 227466, and a third semantics
validator at line 3407368. Below that runtime gate is a harder
compile-time limit on the M1 generation. The M1 task-descriptor encoder
packs the source element format into a two-bit field, which holds only
the integer and half-precision codes and has no bit space for the E4M3
codepoint. Feeding fp8 to the M1 encoder thus aborts the compile rather
than refusing the operation at runtime. The encoder that does have the
E4M3 codepoint widens that field to three bits and adds a distinct
output slot, and that wider encoder is present from the A17 generation
onward even though the runtime capability at 0x52d fires only
on H18. 
 
 
 The operation-side gate matches the encoder, decoded from the compiler
and not measured on an H18 part. The
 MinimumFamily<N> trait that chapter
 35 reads as the
operation-legality floor has a high-N set, a few operations at N=5, N=6,
and N=7, the A16, A17, and A18 floors, and the fp8-bearing operations
are in that set. The fp8 converters and the quant-unit storage are
compiled into the one byte-identical image, so an fp8 operation parses
and type-checks on any target. Native execution depends on both that
high-N family floor and the 0x52d capability byte, which is why
the datapath is present yet inert below H18. 
 
 
 The format-register delta between the M1 and the H18 encoder is exact.
The M1 generation builds the generation-5 and generation-7 descriptors,
whose SetCommonInFmt writes a two-bit field at
 this+0x48 holding only int8, uint8, and fp16, and the code
 0xc aborts with “Error: Invalid Common InFmt E4M3”. The
generation-20 descriptor that the A17 generation builds packs all three
format fields into a 32-bit word at this+0x228 , widening each
lane to three bits. SetCommonInFmt gives E4M3 the source-one
code 4 at bits 2 through 0, SetCommonSrc2InFmt gives it the
source-two code 0x20 at bits 5 through 3, and
 SetCommonOutFmt gives it a distinct output slot 0x100 
at bits 8 through 6. Table   36.3 gives the task-descriptor
format-register delta, showing that the M1 encoder has no bit space for
an E4M3 codepoint while the generation-20 encoder widens each lane to
three bits. 
 
 
 Table 36.3: The task-descriptor format-register delta across the upper-tier
generations. 
 
 
 
 
 
 Field 
 
 
 
 M1 generation-5 at this+0x48 
 
 
 
 H18 generation-20 at this+0x228 
 
 
 
 
 
 
 source-one format 
 
 
 
 two-bit lane, int8, uint8, fp16 only 
 
 
 
 three-bit
lane, plus E4M3 as 4 
 
 
 
 
 source-two format 
 
 
 
 folded into the two-bit space, no
distinct E4M3 code 
 
 
 
 three-bit lane, E4M3 as 0x20 
 
 
 
 
 output format 
 
 
 
 two-bit lane, E5M2 reuses the fp16 slot 0x20 
 
 
 
 three-bit lane, E4M3 as 0x100 
 
 
 
 
 E4M3 codepoint 
 
 
 
 absent, a compile-time assert 
 
 
 
 present
as 4, 0x20 , 0x100 
 
 
 
 
 E4M3 overflow register 
 
 
 
 stub assert on the generation-8 setter 
 
 
 
 this+0x2fc and this+0x300 , bit 24 
 
 
 
 
 
 The overflow mode is a per-source register field on the generation-20
encoder, SetTileDmaSrc1E4M3Overflow writing bit 24 of
 this+0x2fc and SetTileDmaSrc2E4M3Overflow writing bit
24 of this+0x300 , where 1 selects saturate and 0 selects NaN.
On the older encoders the same setter is a stub that asserts
“E4M3Overflow is not supported” only when the overflow option is
engaged. 
 
 
 In the multiply array fp8 is an input width, not an accumulator width.
An E4M3 weight expands to fp16 going into the multiply, the products
accumulate in the same wide register every family uses, and the output
port rounds the result to fp16. No fp8 accumulator type, register field,
or symbol exists in the compiler: the generation-20 format word encodes
only the source-one, source-two, and output element formats, with no
accumulator-format field. E4M3 is a native kernel format, code 6 in the
kernel-format set that ZinSetFormat admits through the mask
 0x3b , alongside int8, uint8, fp16, and fp32; E5M2 is absent
from that set, so it is a conversion and upscaler-input format rather
than a kernel format. Throughput runs on the same double-rate path int8
uses, gated by
 ZinDoubleMacMode::CanUseDoubleMacModeBasedOnFormats . A one-byte
activation against a one-byte kernel of the same numeric class is
eligible for the double-multiply mode, the eligibility being the
exclusive-or term that is true only when the activation-float bit equals
the kernel-float bit. An E4M3 activation against an E4M3 kernel is both
one-byte and both float, so it runs at twice the per-element rate into
the fp16 accumulator, while a mixed int8-against-E4M3 pair is not
eligible. E4M3 is symmetric-only, with the zero point forced to zero,
the same constraint the M1 imposes on int8. The quantize and dequantize
validators reject a zero point with “Zero point is not supported for
quant with E4M3 output format”, and the same rule reaches the palette
layer. E4M3 weights stream as a palette through
 ZinIrWeight::DePalettizeWeightData<e4m3_t> ,
a codebook of E4M3 values indexed by a packed stream at bit-widths 1, 2,
3, 4, 6, and 8. This is the identical machinery the int4, int8, and fp16
palettes use under template specialization, dequantized as scale times
E4M3 with no zero point. 
 
 
 
 36.3 Multi-die collective layer 

 
 Table   36.4 gives the collective operations of the multi-die
dialect, their backend operation classes, and the unit-type code of
each. 
 
 
 Table 36.4: The collective operations of the multi-die dialect, their
backend operation classes, and the unit-type code of
each. 
 
 
 
 
 
 silc mnemonic 
 
 
 
 C++ operation class 
 
 
 
 role 
 
 
 
 unit-type code 
 
 
 
 
 
 
 silc.all_reduce 
 
 
 
 SilcAllReduceOp 
 
 
 
 reduce a tensor
in place across a mesh axis 
 
 
 
 78 
 
 
 
 
 silc.all_gather 
 
 
 
 SilcAllGatherOp 
 
 
 
 concatenate shards into a replicated tensor 
 
 
 
 76 
 
 
 
 
 silc.all_slice 
 
 
 
 SilcAllSliceOp 
 
 
 
 scatter a
replicated tensor into shards 
 
 
 
 75 
 
 
 
 
 silc.mesh 
 
 
 
 SilcMeshOp 
 
 
 
 declare the
device mesh 
 
 
 
 none 
 
 
 
 
 silc.call 
 
 
 
 SilcCallOp 
 
 
 
 per-die single-program call 
 
 
 
 79 
 
 
 
 
 
 The collective layer is a cross-die data path, not the independent
per-job steering a multi-die part otherwise does. The kernel
load-balancer steers whole independent submissions to the least-busy
engine die and never exchanges tensor data between them, and the driver
supports up to four dies. The M1 and the M1 Max each register a single
engine die, so this steering engages only on a multi-die part such as
the Ultra. The compiler’s collective instead splits one tensor across
dies and exchanges partials, threaded through an
 optional<ZinIrDeviceMesh> that
 GetAndValidateSpmdDeviceMesh and
 ZinParseDeviceMeshAttributes build, so a program compiled with
a device-mesh attribute gets a real all-reduce, all-gather, or all-slice
across the mesh rather than per-die placement. The cross-die move itself
is the HandleCcdmaLayer direct-memory-access primitive below,
and ValidateMeshAxesInTensorFamily is the family gate on
whether a given die admits the mesh. This contrast is decode-derived;
whether a two-die Ultra in any reached family accepts the mesh path is a
multi-die measurement this guide does not have. 
 
 
 It is a distinct intermediate-language dialect, mlir::silc ,
whose closed operation set is the three collectives above over a device
mesh, plus the mesh declaration and the per-die call. The
operation-class list is exactly these, with no reduce-scatter and no
broadcast, the all-slice operation standing in for the scatter. The
collective operations have the attributes mesh ,
 mesh_axes , sharding , the members membership
list, and reduce_op . 
 
 
 The reduction kind is an enumerated attribute decoded directly from the
packed-string compare in symbolizeReductionKind , which
 table   36.5 gives token by token. 
 
 
 Table 36.5: The reduction-kind enumeration the all-reduce reduce-operation
attribute holds. 
 
 
 
 Token 
 Integer 
 
 
 
 sum 
 1 
 
 max 
 2 
 
 min 
 3 
 
 product 
 4 
 
 mean 
 5 
 
 miss 
 0, invalid 
 
 
 
 
 The mesh is an N-dimensional grid of dies by engines-per-die, a vector
of per-axis extents held in ZinIrDeviceMesh , which exposes the
die count, total engine count, and engines-per-die count. A device
identifier maps to a mesh coordinate and an engine index by a
mixed-radix split at the die axis, which
 ZinSPMDUtils::AneIndexFromDeviceId computes: 
 
 
 

 
 
 ane = ∑ i ≥ d id ⁡ [ i ] ​ ∏ j > i , j ≥ d ext ⁡ [ j ] + ( ∑ i < d id ⁡ [ i ] ​ ∏ j < i ext ⁡ [ j ] ) ⋅ anesPerDie \mathrm{ane}=\sum_{i\geq d}\mathrm{id}[i]\prod_{j>i,\,j\geq d}\mathrm{ext}[j]\;+\;\left(\sum_{i<d}\mathrm{id}[i]\prod_{j<i}\mathrm{ext}[j]\right)\cdot\mathrm{anesPerDie} 
 
 
 
 
 where d d is the die-axis split index: the axes above the die axis
fold into the within-die engine offset, and the axes below fold into the
die index, multiplied by engines-per-die. The inverse decode is
 DeviceIdFromAneIndex . A layer runs on a die through
 ZinEngineLayer::RunsOnDeviceId . A layer not assigned to the
single-program path runs on all dies. Otherwise it emits on a die only
when the engine index for that die is a key in the layer’s engine-set
map, which is how the members attribute becomes a per-die emit
decision. 
 
 
 A sharding attribute maps each tensor axis to a mesh axis, splitting
that axis into one shard per device along the axis. The split requires
even divisibility, which the strings “Input tensor dimension must be
divisible by the number of shards along the tensor dimension” and
“Kernel dimension must be divisible by number of shards” enforce. The
compiler rejects sharding the same mesh dimension twice and allows a
replicated section only on a multi-die network. 
 
 
 The reduce-across-the-mesh operation lowers to a collective
direct-memory-access that holds a hardware atomic read-modify-write: the
reduction happens in memory as the direct-memory-access writes into a
shared buffer, which is why the operation requires in-memory-reduction
support that the single-die families lack. The reduction-to-atomic map
is decoded from the ZinIrReductionTypeToZinAtomicOpType switch,
which table   36.6 gives along with the reductions that have no
hardware atomic and are rejected. 
 
 
 Table 36.6: The reduction-type-to-atomic-operation register map for the
all-reduce collective, with the reductions that have no hardware atomic
and are rejected. 
 
 
 
 Reduction type 
 Atomic-op register value 
 
 
 
 1 
 4 
 
 2 
 3 
 
 4 
 1 
 
 5 
 2 
 
 8 
 5 
 
 9 
 6 
 
 10 
 7 
 
 3, 6, 7, 11 
 assert, no hardware atomic 
 
 other 
 0 
 
 
 
 
 The atomic configuration packs as
 (atomicOp & 0xff) | (atomicDataType << 8) ,
and the input supplied to the collective must arrive through a bypass
pass-through, asserted by “Input to inter-die AllReduce should be
NEBypass”. The all-reduce lowering itself further asserts “AllReduce
is currently not supported for architectures that do not support
in-memory reductions”. 
 
 
 HandleCcdmaLayer<Nu> programs the
collective direct-memory-access into the task descriptor, instantiated
for the generations { 1 , 4 , 5 , 6 , 7 , 8 , 10 , 11 , 17 , 19 , 20 } \{1,4,5,6,7,8,10,11,17,19,20\} . Each
opens with the collective-enable gate and the per-die predicate before
driving the setters in a fixed order. That order is the source mode, the
counter mode, the data size, five shape words, four destination strides,
the destination base address, the optional constant, four source
strides, the source base address, the wait-event address from the mesh
symbol, the counter address, the atomic data type, the atomic operation,
the counter amount, and the wait-event value. The base addresses are all
emitted through ZinSPMDUtils::GetSymbolOffsetToBaseAddr , the
extended-addressing path that needs the cross-die address-reach byte. 
 
 
 The layer is decoded but inert in the compiler this guide reads. Every
collective direct-memory-access register setter is a stub that asserts
“CCDMA is not supported for this arch”, in every task-descriptor
generation present including generation 20, the would-be Ultra path: the
body calls the full setter sequence, but the setters abort. The
collective-enable capability byte at offset 0x48b reads zero on
all twenty-eight targets including the M-class and Ultra-reference
targets. Table   36.7 gives the collective and cross-die
capability bytes decoded across the twenty-eight targets, with the
collective-enable byte clear everywhere. 
 
 
 Table 36.7: The collective and cross-die capability bytes decoded across
the twenty-eight targets, with the collective-enable byte clear
everywhere. 
 
 
 
 
 
 Byte 
 
 
 
 Capability 
 
 
 
 Floor 
 
 
 
 M1 (H13) 
 
 
 
 A14 
 
 
 
 A15 
 
 
 
 M5 (H17s) 
 
 
 
 H18 
 
 
 
 M-class 
 
 
 
 
 
 
 0x48b 
 
 
 
 collective-enable 
 
 
 
 none in this build 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 
 0x55c 
 
 
 
 cross-die extended addressing 
 
 
 
 A14 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 mixed, M11 and U2, U3 set, U1 clear 
 
 
 
 
 0x564 
 
 
 
 multi-die hazard tracking 
 
 
 
 A14 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 1 
 
 
 
 0 
 
 
 
 0 
 
 
 
 
 0x687 
 
 
 
 multi-die remote dependency 
 
 
 
 A15 
 
 
 
 0 
 
 
 
 0 
 
 
 
 1 
 
 
 
 1 
 
 
 
 0 
 
 
 
 0 
 
 
 
 
 0x4a4 
 
 
 
 M-class secondary cap 
 
 
 
 M-class only 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 0 
 
 
 
 1 
 
 
 
 
 
 The compiler thus has the front end of the collective in full: the
operation set, mesh and sharding math, reduction-to-atomic map, and
per-die dispatch. No family in this compiler arms the register encoding
that would drive the engine. 
 
 
 A second-layer gate is in the source-direct-memory-access emitters,
where the single-program flag drives an assert “This target does not
allow sharding or SPMD functions”. A third gate in the tasklet emitter
asserts “No tasklet for given architecture” when the per-section
tasklet bit and the single-program predicate are not both set. On the M1
all three gates fail, so the M1 is single-die. 
 
 
 The pieces the single-die M1 silicon does touch are the on-die ordering
bits the same machinery shares. Those bits are the layer-two barrier,
event masks, and remote-dependency bookkeeping, none of which is the
cross-die reduction itself. On the M1 generation-10 descriptor the
layer-two barrier sets bit 23 of TD+0x134 and the forward
barrier sets bit 30. The event setter writes a 26-bit signal mask into
 TD+0x10 and a 26-bit wait mask into TD+0x18 , and a
direct-memory-backed event is rejected with “DRAM Events not supported
for architecture”. The distributed unit is the tasklet, the multi-die
variant of the descriptor instruction, one tasklet per participating
die. 
 
 
 
 36.4 What requires newer parts 

 
 The fp8 datapath requires an H18-class part to set the capability byte
and exercise the native E4M3 multiply. The collective layer requires a
multi-die part and a newer compiler that arms the collective-enable byte
and replaces the register stubs with a real encoding. Until that
hardware and that compiler are in hand, the encodings here stand as the
predicted upper tier of the line. 
 
   
 
 Back Matter 
   
 
 Methodology 
 
 
 The measured silicon, the tools, and what each technique can and cannot observe. 
 
 
 Open questions 
 
 
 The findings that remain unconfirmed and what would settle each. 
 
 
 Statements 
 
 
 Provenance, reproduction, and the work’s declarations. 
 
 
 
 
 
 Methodology 

 
 
 SUMMARY 
 Every finding rests on one of four techniques: a direct private-runtime
path, static decompilation of the stack, live read-only instrumentation,
and compile-and-run probing. The results rest on two measured silicon
points, M1/H13 as the primary host and M5/H17s as the second, with
claims marked as measured on a named generation or as predicted. 
 
 
 
 Every quantitative claim in this guide is either measured on running
silicon, read out of a binary or table, or marked as predicted from
those artifacts. This chapter states how the engine was reached and how
it was characterized. The four converging lines of evidence behind the
findings are the direct private-runtime path, static decompilation, live
instrumentation, and cross-silicon measurement, which
 figure   1 shows against the engine. 
 
 
 Figure 1: The four lines of evidence behind the guide findings. 
 
 
 Reaching the engine 

 
 The engine was reached without the public model framework. The same
private Espresso and dispatch runtime that the system’s own dispatchers
use is callable from ordinary user space. No high-level framework is in
the path, and the operations the compiler accepts need no special
entitlement. The compiler lowers a graph to the engine’s program format,
and the runtime loads it and drives it through an execution stream
directly. This route bypasses the public compute-unit selector
 [AppleCoreML] and holds every measured
result in the guide. 
 
 
 In-process instrumentation mapped the dispatch path: a library inserted
into the dispatching process interposed on the kernel-driver calls. The
mapping showed the dispatch as input and output surfaces passed to an
asynchronous driver selector, and it located the boundary below which
user space cannot see. 
 
 
 
 Static analysis of the
stack 

 
 Decompilation and static analysis of four artifacts read out the
structure of the stack, which table   1 pairs with what
static analysis recovered from each. 
 
 
 Table 1: The four decompiled artifacts of the stack and what static
analysis read out of each. 
 
 
 
 
 
 Artifact 
 
 
 
 What was read out 
 
 
 
 
 
 
 the dispatch and compiler runtime 
 
 
 
 the operation vocabulary, the
compiler passes, and the program bundle format 
 
 
 
 
 the kernel driver 
 
 
 
 the user-to-kernel boundary and the
expanded program binary it lowers 
 
 
 
 
 the engine firmware 
 
 
 
 the on-engine execution model and the
host-to-firmware command protocol 
 
 
 
 
 the intermediate-language operation set 
 
 
 
 the lowering
from the public operation set to the engine’s own 
 
 
 
 
 
 Apple distributes the firmware on the M1 unencrypted, an ARM64
real-time-kernel image behind an image wrapper. Its execution loop, its
driver, and its ninety-three-command host protocol were decoded
statically rather than inferred. The compiler lowers a graph to a
ninety-seven-operation internal vocabulary that is a superset of the
public set. Static reading of those passes separated the hidden internal
operations from the user-reachable ones. 
 
 
 
 Live instrumentation 

 
 Three escalating instruments supplied the running values that static
reading cannot recover, each read-only or recoverable on a dedicated
host. A user-space counter interface exposed live hardware counters:
DRAM bytes moved, energy in millijoules, and clock frequency. Sampling
those counters around a hot loop gave the roofline directly. That fixed
the M1 at about 12 fp16 TFLOP/s of compute, about 85 GB/s of DRAM
bandwidth, and near 0.5 pJ per FLOP sustained, 0.37 at the compute
optimum. It also fixed a 2 MB on-chip working-set threshold, confirmed
by the counters falling off exactly where the working set crosses 2 MB.
A signpost trace on the engine subsystem gave the op-level event
sequence and independently confirmed the bundle finding that each
dispatch wraps three driver requests. 
 
 
 The lowest-level instrument was kernel tracing with boot security
lowered on a wipeable development machine. Read-only function-boundary
tracing instrumented over a hundred thousand kernel probes, about
eighteen hundred of them inside the engine driver, with no driver
extension and no crash class. That trace captured the expanded program
binary that does not exist on disk. The binary is a sectioned executable
lowered below user space whose program section is a list of
forty-four-byte records, each one a register write that wires a buffer
address into a direct-memory-access engine. 
 
 
 
 Attestation versus
reachability 

 
 A capability listed in a hardware table or accepted by the frontend
attests existence, not that the engine will run it. Only a
compile-and-run on the target confirms a capability. One case forced the
rule: the hardware abstraction layer advertises three-dimensional
convolution and the intermediate language recognizes it, yet it fails
backend lowering on every device mask and never reaches the engine.
Two-dimensional convolution, fused attention path, normalization family,
and activation and reduction set appear here because they survived
compile-and-run probing, not because a capability bit promised them. The
same rule, read off the counters and the device mask, separates
operations that compile but route to the CPU or GPU from operations that
run on the engine. 
 
 
 
 What each technique cannot
see 

 
 The boundaries do not overlap. Table   2 pairs each
characterization technique with what it observes and the boundary it
cannot cross. 
 
 
 Table 2: Each characterization technique paired with what it observes
and the boundary it cannot
cross. 
 
 
 
 
 
 Technique 
 
 
 
 What it observes 
 
 
 
 What it cannot observe 
 
 
 
 
 
 
 decompilation and static analysis 
 
 
 
 code structure, formats,
vocabularies, command and register tables 
 
 
 
 runtime values, and any data
the firmware computes rather than stores 
 
 
 
 
 user-space hardware counters 
 
 
 
 aggregate power, energy,
bandwidth, and frequency around a loop 
 
 
 
 per-operation register-level
timing, which is gated below the dispatch layer 
 
 
 
 
 signpost and dispatch tracing 
 
 
 
 the op-level event order and the
three-request dispatch shape 
 
 
 
 the expanded program, which is lowered
below user space 
 
 
 
 
 kernel function-boundary tracing 
 
 
 
 the expanded program
binary and the section layout it lowers 
 
 
 
 the semantic identity of an
individual register, virtualized per load by the memory-management
unit 
 
 
 
 
 compile-and-run on the target 
 
 
 
 what the engine accepts and runs, and
its numeric output 
 
 
 
 another generation’s behavior, which requires that
chip to measure 
 
 
 
 
 
 The last unmapped item is the name of each individual silicon register.
Its address is a per-load device address that the memory-management unit
remaps on every load, the firmware writes it through a generic writer
with no address-to-name table, and the per-offset naming is
undocumented. What remains is a labeling gap behind address
virtualization and undocumented silicon, not a deeper layer left
uncaptured. 
 
 
 
 Two measured silicon
points 

 
 Two generations were measured directly, and they anchor the
cross-generation claims. The M1, internally H13, is the primary
measurement host. It fixed the roofline, unencrypted firmware decode,
kernel capture of the expanded program down to the register-write
records, operation-conformance set, and all four axes of the fp16
divergence model. It is also where the system-wide compile service was
characterized. A rapid burst of compile crashes spaced faster than the
daemon’s ten-second relaunch drives an unrelated control compile from
120 ms to a multi-minute hang. This is a rate condition rather than a
per-crash leak, recoverable only by terminating the daemon. 
 
 
 The M5, internally H17s, is the second measured point and confirmed the
cross-generation scaling. It established that the numeric divergence
accumulates to at most a fraction of a percent over a full training run,
that the family-wide capability limits are not specific to one chip, and
that the operation set is portable across the generations. A capability
table can be cross-compiled statically for an unmeasured generation, but
only the chip itself confirms its numerics. 
 
 
 The M5 ran with System Integrity Protection enabled, the shipping
configuration, while the lowest-level M1 instrumentation lowered boot
security. Security and isolation claims therefore take the M5 as the
authoritative point, since it reports the entitlement gates, exclave
boundary, and counter access a normal client meets under the enforced
configuration rather than what a lowered-security system exposes. 
 
 
 
 Reproducing the
measurements 

 
 Every headline number maps to one command and one committed result file,
taken in a fixed environment. The measurements were taken with
ANECompiler 9.509.0, whose intermediate-language component is versioned
3520.4.1, on macOS 14 or later (verified on macOS 26.5), with Python
3.10 or later (developed and verified on Python 3.14), and with numpy as
the only core numeric dependency. Python 3.10 is the floor because
several core modules use PEP 604 union syntax in runtime-evaluated
signatures. 
 
 
 The reproduction has two layers. A single top-level driver script runs
the full sequence and is fail-soft: it reports and skips a device or
power step that cannot run, so the deterministic claims still reproduce.
Beneath it are the individual measurement harnesses, each producing a
committed result file, so a paper claim resolves to a command and to a
stored result. A capability smoke test and an operation smoke test
confirm that the closed capability set and every released operation
compile and run on the engine. A corpus runner is the correctness gate
that the optimizer is held to. A device-comparison harness records
latency and speed-per-watt across the engine, GPU, and CPU; a roofline
harness records the saturation and bandwidth ceilings. Both harnesses
write JSON result files that the committed roofline analysis and figure
are built from. 
 
 
 Several limits bound how the numbers should be read. 
 
 
 
 • 
 
 The per-rail power figures come from the system power estimator,
 powermetrics , which reports a modeled estimate rather than an
independent wall-meter measurement. There is no separate validation of
that estimator: the reported total-package active power with idle
subtracted is a calibrated estimate, not a metered reading. 
 
 • 
 
 The work runs on Apple silicon only. It installs on any platform but
cannot run without an Apple silicon Mac and the built dispatch
library, and there is no CPU, GPU, or other fallback for the engine
path. 
 
 • 
 
 The path calls private Apple framework symbols tied to ANECompiler
9.509.0. A macOS update can break the dispatch-library build or the
dispatch path, and none of it is an Apple API contract. 
 
 • 
 
 Determinism splits by claim type. The capability census, operation
conformance check, operation smoke test, and correctness corpus are
deterministic pass-or-fail gates; the device-comparison, serving, and
roofline numbers are measurements and vary run to run. 
 
 
 
 
 
 
 Open questions 

 
 
 SUMMARY 
 Open questions fall into three kinds: questions another chip or an
on-silicon probe would answer, questions the sanctioned entitlement
would answer, and questions that are impossible to answer because the
data does not exist or the silicon leaves no observable trace. Each item
gives why it is open and what would close it. 
 
 
 
 The engine is decoded from the host call down to the register writes,
and everything that exists as bytes or strings has been resolved into
human-readable form. Two silicon points are measured directly: M1/H13
and M5/H17s. M5/H17s confirmed all ten cross-silicon predictions on
device. The M3/H15 generation and the upper tier above H17s are
decompile-derived, not measured. M5/H17s closes none of the upper-tier
items, because it is a 16-core H17s part rather than the H17d 64-core
ceiling, H18-gated fp8 runtime, or Ultra multi-die collective. 
 
 
 Why an item is open 

 
 Each open item falls into one of three kinds, which set the three tables
below. A chip-measurement item has its structure decoded but needs
another generation, the upper tier, or an on-silicon probe to read the
realized values. An entitlement item is attested in the
hardware-abstraction layer or the intermediate language but is reachable
only through the sanctioned model path. An impossible item cannot be
resolved at all: either the data does not exist, or the behavior is
irreducible silicon that leaves no trace in any result and no artifact
to decode. 
 
 
 
 Ledger 

 
 Three tables sort the open items by how each could be resolved.
 Table   3 gives the items another chip or an on-silicon
probe would resolve, each with its decoded structure and the measurement
that would close it. 
 
 
 Table 3: Open items a further on-silicon measurement would resolve: the
structure is decoded, the realized values need the part or the
probe. 
 
 
 
 
 
 Open item 
 
 
 
 Why it is open 
 
 
 
 What would close it 
 
 
 
 
 
 
 Live values of the single-shot fault and translation-fault capture
registers 
 
 
 
 The registers are located (four fault descriptors and a
status word at engine+0xe028) and the ANE-side handler has a benign
branch, but the IODART substrate panics on a real fault, so the live
values are uncaptured 
 
 
 
 A fault path that recovers instead of panicking
the IODART substrate 
 
 
 
 
 Realized A15 / M3 / H15 silicon behavior 
 
 
 
 The dedicated
A15 compiler branch is decoded (its cost table, its 45-operation family
set, the full H15 targets, the YUV420 input it alone accepts), only the
realized numbers need the part 
 
 
 
 On-chip measurement of an H15 part 
 
 
 
 
 Realized upper-tier behavior: 64-core H17d, H18-gated fp8 datapath,
Ultra multi-die collective 
 
 
 
 The encodings are decoded (the core-count
parameter, the fp8 e4m3 and e5m2 convert-and-quantize path, the Ultra
device-mesh collective) and the upper tier adds only cores over A16, no
new operations, but none of it materializes without the part 
 
 
 
 An H17d,
H18, or Ultra part 
 
 
 
 
 Set behavior of the family-gated abstraction-layer
fields 
 
 
 
 The fields are named and the silicon-capability subset is
complete, their set behavior needs later silicon 
 
 
 
 A part where the gate
is on, for example the A18 or H17-plus FIFO-mode field 
 
 
 
 
 Per-state frequency and voltage of the operating-point sequence 
 
 
 
 The
engine has no local DVFS and is driven by the SoC power controller, the
firmware seven-step credit sequence is recovered, the per-state
frequency and voltage stay behind the opaque power-management base 
 
 
 
 A
power-management-side probe 
 
 
 
 
 
 Table   4 gives the items the sanctioned entitlement
would resolve, attested in the binaries but gated off the direct path. 
 
 
 Table 4: Open items the sanctioned entitlement would resolve, attested
but gated off the direct
path. 
 
 
 
 
 
 Open item 
 
 
 
 Why it is open 
 
 
 
 What would close it 
 
 
 
 
 
 
 Live per-run firmware performance-counter values 
 
 
 
 The read path and its
gate are decoded (the aned daemon clears the stats mask for a
third-party client, and a host-side null check skips the buffer on the
unentitled path), only the live values need the entitled output buffer 
 
 
 
 The entitled path that supplies the output buffer 
 
 
 
 
 Entitled-only features: 3-D convolution, native state
and ring buffer, bf16 program input and output, flexible shapes 
 
 
 
 Attested in the hardware-abstraction layer but unreachable on the direct
path 
 
 
 
 The sanctioned model path that can reach them 
 
 
 
 
 
 Table   5 gives the items that cannot be resolved: the
data does not exist, or the behavior is irreducible silicon that leaves
no trace in any result. 
 
 
 Table 5: Open items that cannot be resolved externally: irreducible
silicon behavior, or data that does not
exist. 
 
 
 
 
 
 Open item 
 
 
 
 Why it cannot be resolved 
 
 
 
 
 
 
 Gate-level MAC and adder-tree wavefront skew 
 
 
 
 The output is
order-independent, so no result reveals the per-cycle wiring, which sits
below the timing floor; only Apple’s register-transfer netlist would
show it 
 
 
 
 
 Exact fp16 partial-sum rounding order within one MAC
reduction 
 
 
 
 The wide accumulator makes the output bit-identical for any
summation order, so the internal sequence leaves no trace; only the
register-transfer netlist would show it 
 
 
 
 
 No flat numeric error or status enumeration 
 
 
 
 Status is held by
notification names and positional indices, not a stored enum; the flat
enumeration does not exist 
 
 
 
 
 The execution-loop state labels 
 
 
 
 The five states are
reconstructed from handler behavior; no name table exists in firmware 
 
 
 
 
 
 
 Form of the residual 

 
 The impossible items are few: the gate-level reduction wavefront and the
internal fp16 rounding order are irreducible silicon, and the flat
status enumeration and the execution-loop state labels do not exist as
stored data. Everything else is decoded in structure and waits only on a
part, a probe, or the entitled path: the chip-measurement items the
tables above list, and the entitlement items attested in the binaries
but gated off the direct path. Static analysis closed the firmware
address rebase that once sat at the host and firmware boundary, and the
M5 measurement confirmed the cross-silicon model without reaching any of
the parts the hardware items need. 
 
 
 
 
 Statements 

 
 Author 

 
 Spencer Bryngelson, Georgia Institute of Technology. Correspondence:
 shb@gatech.edu . 
 
 
 
 Data and code availability 

 
 ANEForge, the open-source code artifact accompanying this guide, is at
 https://github.com/comp-physics/ANEForge , described in
 arXiv:2606.17090 .
Appendix E records the provenance of
every substantive claim, measured or decompile-derived, and the
methodology summarizes it. 
 
 
 
 Ethics and responsible
disclosure 

 
 The work reported here is reverse engineering conducted on the author’s
own Apple hardware, by static decompilation and on-device measurement,
for interoperability and research. The guide redistributes no Apple
source code or proprietary binaries; it documents facts about the
hardware and its interfaces. The direct route it describes is
undocumented, unsupported, and version-fragile, and is intended for
measurement, research, and on-device work, not for shipping software,
where Core ML remains the supported path. 
 
 
 
 Funding 

 
 This was independent work and received no external funding. 
 
 
 
 Competing interests 

 
 The author declares no competing interests. This is an independent work
and is not affiliated with, authorized by, or endorsed by Apple Inc. 
 
   
 
 Appendices 
   
 
 A    Operation-by-device matrix 
 
 
 Every operation against every device, native or decomposed. 
 
 
 B    Hidden-layer catalog 
 
 
 The native layers and their descriptors, with parameters and symbols. 
 
 
 C    Decoded reference tables 
 
 
 The enum tokens, structs, status codes, register map, and program schema. 
 
 
 D    Glossary 
 
 
 The terms, the family and silicon map, and the core facts to read first. 
 
 
 E    Provenance 
 
 
 The evidentiary basis of every claim, Part by Part and chapter by chapter. 
 
 
 
 
 
 Appendix A Operation-by-device matrix 

 
 
 SUMMARY 
 This appendix is the full per-operation, per-family status reference
behind chapter 4 . Read down a family
column to see what compiles and runs on that chip, and read the status
marks and note for the gate and the route. 
 
 
 
 Each row is one intermediate-language operation, grouped by operation
class, with its status on each Mac engine family from the M1 through the
M5. Chapter 4 summarizes this table; the
cells here are the reference. 
 
 
 The status marks are fixed: 
 
 
 
 • 
 
 Native: the operation compiles and runs on that family on the direct
engine path. 
 
 • 
 
 Family-gated: no path on the listed family, native from the family
named in the note. 
 
 • 
 
 Bridge: reachable only through a decompose, software fallback, or
compiler-internal route, never as a standalone code-generated
operation. 
 
 • 
 
 No path: rejected on every family from the M1 through the M5, computed
off-engine. 
 
 
 
 
 The family columns are M1 (H13, A13), M2 (H14, A14), M3 (H15, A15), and
M4 and M5 (H16 and H17s, A16 and A17). The A11 and A12 engines are below
the floor that runs any of this vocabulary and are out of scope for the
table. 
 
 
 The M1, M2, and M5 columns are measured on physical silicon. The M3
column and the M4 part of the merged M4 and M5 column are
decompile-derived predictions from the per-chip tables, so a per-cell
status there is a predicted capability rather than a measured one. 
 
 
 The table covers the 187 intermediate-language operations the compiler
exposes. Of these, about 108 are native on the M1: the full elementwise,
compare, activation, convolution, pooling, structural, and quantization
vocabulary, plus the reduction, normalization, softmax, square-root
family, fused attention, tile, and space-channel set. Nine need the M2
or later: the texture-engine operations (crop-resize, resample, affine,
hardware gather) and the rank and sort bridge (top-k, sort, dynamic
slice). Four need the M3 or later: native sin and cos ,
the hardware random generator, and the whole-tensor argument reductions
on the intermediate-language route. Thirty-seven are rejected on every
family and decompose on the host. About twenty-four are
compiler-internal: mapped but with no observed standalone code
generation, reachable only inside a wrapping construct. 
 
 
 A.1 Per-chip numeric limits 

 
 The status of an operation is one axis; the numeric envelope it runs in
is the other. Table   A.1 gives that envelope across
the five capability tiers, measured from the live compiler by calling
every per-architecture parameter constructor on a single M1, and a dash
marks an unsupported value. The older column is the pre-A13
legacy targets the compiler still has parameter tables for, below the
floor of the operation-status table above. 
 
 
 Table A.1: The per-chip numeric limits of the engine, measured from the
live compiler across the five capability
tiers. 
 
 
 
 
 
 Limit 
 
 
 
 older 
 
 
 
 M1, A13 
 
 
 
 A14 
 
 
 
 A15 
 
 
 
 A16, M5 
 
 
 
 
 
 
 max kernel W (default format, large) 
 
 
 
 29 
 
 
 
 29 
 
 
 
 32 
 
 
 
 32 
 
 
 
 32 
 
 
 
 
 max kernel W (fp16, large) 
 
 
 
 13 
 
 
 
 13 
 
 
 
 16 
 
 
 
 16 
 
 
 
 16 
 
 
 
 
 max kernel W (default, small) 
 
 
 
 15 
 
 
 
 15 
 
 
 
 16 
 
 
 
 16 
 
 
 
 16 
 
 
 
 
 max kernel W (fp16, small) 
 
 
 
 7 
 
 
 
 7 
 
 
 
 8 
 
 
 
 8 
 
 
 
 8 
 
 
 
 
 min kernel W (default / fp16, large) 
 
 
 
 16 / 8 
 
 
 
 16 / 8 
 
 
 
 1 / 1 
 
 
 
 1 / 1 
 
 
 
 1 / 1 
 
 
 
 
 max kernel H (large / small) 
 
 
 
 29 / 15 
 
 
 
 29 / 15 
 
 
 
 32 /
16 
 
 
 
 32 / 16 
 
 
 
 32 / 16 
 
 
 
 
 max kernel D (large / small) 
 
 
 
 1 / 1, no 3D 
 
 
 
 16 / 8 
 
 
 
 16 / 8 
 
 
 
 16 / 8 
 
 
 
 16 / 8 
 
 
 
 
 max patch W / H / D 
 
 
 
 15 / 15 / 0 
 
 
 
 28 / 28 / 15 
 
 
 
 31 /
31 / 15 
 
 
 
 31 / 31 / 15 
 
 
 
 31 / 31 / 15 
 
 
 
 
 max tensor W / H 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 65536 
 
 
 
 
 max tensor D 
 
 
 
 1 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 65536 
 
 
 
 
 max tensor C 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 
 max tensor N (batch) 
 
 
 
 4096 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 65536 
 
 
 
 
 max transpose W / H 
 
 
 
 0, always split 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 16384 
 
 
 
 65536 
 
 
 
 
 reduction-to-transpose threshold 
 
 
 
 none 
 
 
 
 192 
 
 
 
 192 
 
 
 
 384 
 
 
 
 384 
 
 
 
 
 group-conv decompose limit (Cin ⋅ \cdot kW ⋅ \cdot kH) 
 
 
 
 64 
 
 
 
 2048 
 
 
 
 2048 
 
 
 
 2048 
 
 
 
 2048 
 
 
 
 
 stride factor list 
 
 
 
 [2,3,4,8] 
 
 
 
 [2,3,4,8] 
 
 
 
 [2,3,4,8] 
 
 
 
 [2,3,4,8] 
 
 
 
 [2,3,4,8] 
 
 
 
 
 matmul SRAM working set 
 
 
 
 2 MB, M9 1 MB 
 
 
 
 2 MB 
 
 
 
 2 MB 
 
 
 
 2 MB 
 
 
 
 2 MB 
 
 
 
 
 DMA width granule 
 
 
 
 16 B 
 
 
 
 16 B 
 
 
 
 16 B 
 
 
 
 16 B 
 
 
 
 16 B 
 
 
 
 
 patch-width floor / max 
 
 
 
 none 
 
 
 
 16 / 512 px 
 
 
 
 16 / 512 
 
 
 
 16 / 512 
 
 
 
 16
/ 512 
 
 
 
 
 instruction alignment 
 
 
 
 256 B 
 
 
 
 256 B 
 
 
 
 16 B 
 
 
 
 16 B 
 
 
 
 16
B 
 
 
 
 
 has texture engine 
 
 
 
 no 
 
 
 
 no 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 yes 
 
 
 
 
 kernel-memory budget 
 
 
 
 64 KB 
 
 
 
 64 KB 
 
 
 
 64 KB 
 
 
 
 64 KB 
 
 
 
 64 KB 
 
 
 
 
 activation-LUT budget 
 
 
 
 150 B 
 
 
 
 86 B 
 
 
 
 86 B 
 
 
 
 86 B 
 
 
 
 86 B 
 
 
 
 
 context-switch live-tensor limit 
 
 
 
 2 
 
 
 
 2 
 
 
 
 ∞ \infty 
 
 
 
 ∞ \infty 
 
 
 
 ∞ \infty 
 
 
 
 
 
 The four generational dividing lines are visible in this table. The M1
adds the depth and three-dimensional axis and every reduction-class
operation. The A14 adds the texture engine. The A15 raises the
reduction-to-transpose threshold from 192 to 384 and adds native
trigonometry. The A16 quadruples the maximum tensor and transpose
dimensions from 16384 to 65536. 
 
 
 
 A.2 Convolution, matrix multiply, and
pooling 

 
 Table   A.2 lists the convolution, matrix-multiply,
and pooling operations with their per-family status and the lowering
note for each. 
 
 
 Table A.2: Convolution, matrix-multiply, and pooling operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 conv 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 M1 kernels up to
29x29, M5 up to 32x32; Winograd auto-selected for eligible 3x3 stride-1
convs 
 
 
 
 
 conv_transpose 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Deconvolution; strided axes use the small-kernel caps 
 
 
 
 
 linear 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Folds to
convolution when the right operand fits the on-chip working set 
 
 
 
 
 linear_activation 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Fused linear and activation 
 
 
 
 
 matmul 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Engine lane or
convolution fold; same tensor caps as convolution 
 
 
 
 
 ne_matmul 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Private engine-lane matrix-multiply unit 
 
 
 
 
 einsum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lowers to a matmul
and transpose chain 
 
 
 
 
 ne_conv 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Private engine-lane convolution unit 
 
 
 
 
 avg_pool 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Window up to 29
on the M1, up to 31 from the M2 
 
 
 
 
 max_pool 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 l2_pool 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table
pool 
 
 
 
 
 ne_pool 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Private engine-lane pooling unit 
 
 
 
 
 pe_pool 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Private
planar-engine pooling unit 
 
 
 
 
 pe_elementwise 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Private planar-engine elementwise unit 
 
 
 
 
 pe_goc 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Private
planar-engine gain-offset unit, compiler-internal 
 
 
 
 
 ne_bypass 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Private engine-lane bypass unit, compiler-internal 
 
 
 
 
 scaled_dot_product_attention 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Runs on the matmul and softmax path, not texture-gated 
 
 
 
 
 
 The ne_ and pe_ rows are private engine-lane and
planar-engine unit selections of the same convolution, matrix-multiply,
pooling, and elementwise atoms, not separate operations. 
 
 
 
 A.3 Normalization 

 
 Table   A.3 gives the normalization operations, native on every
family from the M1. 
 
 
 Table A.3: Normalization operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 batch_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Inference
fold-to-affine; native statistics form from the M1 
 
 
 
 
 layer_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 instance_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 l2_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 local_response_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Measured on the M1 
 
 
 
 
 
 
 A.4 Elementwise arithmetic 

 
 Table   A.4 gives the elementwise arithmetic operations,
where only mod takes no engine path. 
 
 
 Table A.4: Elementwise arithmetic operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 abs 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 add 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Constant and tensor forms 
 
 
 
 
 sub 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lowered to add of a
negated constant 
 
 
 
 
 mul 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Constant and tensor forms 
 
 
 
 
 real_div 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 General
divide 
 
 
 
 
 floor_div 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table assisted 
 
 
 
 
 pow 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 square 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 sqrt 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table
activation 
 
 
 
 
 rsqrt 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 inverse 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Reciprocal
lookup-table 
 
 
 
 
 maximum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 minimum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 mod 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose on host 
 
 
 
 
 cumsum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native through a
curated runtime path, not the standard compile path; M1 measured 
 
 
 
 
 
 
 A.5 Comparison and logical 

 
 Table   A.5 gives the comparison and logical
operations, the bitwise-logical ones decomposing on the host. 
 
 
 Table A.5: Comparison and logical operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 equal 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 not_equal 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 greater 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 greater_equal 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 less 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 less_equal 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 logical_not 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 select 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The where operation 
 
 
 
 
 logical_and 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose through minimum or multiply on host 
 
 
 
 
 logical_or 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Decompose through maximum on host 
 
 
 
 
 logical_xor 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose through not-equal on host 
 
 
 
 
 
 
 A.6 Activations 

 
 Table   A.6 gives the activation operations, native on
every family and most lookup-table backed. 
 
 
 Table A.6: Activation operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 relu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 relu6 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 leaky_relu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 prelu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Per-channel slope; native at rank 3 or above 
 
 
 
 
 clamped_relu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 thresholded_relu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 threshold 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 clip 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The
clamp operation 
 
 
 
 
 elu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 sigmoid 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Includes the hard variant 
 
 
 
 
 sigmoid_hard 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 tanh 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 scaled_tanh 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 gelu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table approximation 
 
 
 
 
 silu 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Also named swish;
lookup-table 
 
 
 
 
 softmax 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 softplus 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 softplus_parametric 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 softsign 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 erf 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 exp 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 exp2 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 log 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 sign 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 ceil 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 floor 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table 
 
 
 
 
 round 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Round-to-nearest
lookup-table 
 
 
 
 
 
 
 A.7 Reduction 

 
 Table   A.7 gives the reduction operations, where
 reduce_argmin is gated and reduce_prod takes no
path. 
 
 
 Table A.7: Reduction operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 reduce_sum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Reduced axis
at or above 192 takes the transpose route, at or above 384 from the
M3 
 
 
 
 
 reduce_mean 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reduce_max 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reduce_min 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reduce_sum_square 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The
reduce-then-square fusion is M2 onward; the M1 emits an extra fp16
round 
 
 
 
 
 reduce_l1_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reduce_l2_norm 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reduce_log_sum 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table assisted 
 
 
 
 
 reduce_log_sum_exp 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Lookup-table assisted 
 
 
 
 
 reduce_argmax 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Per-axis argmax on all families 
 
 
 
 
 reduce_argmin 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Per-axis
argmin; the intermediate-language route is gated to the M3, the bridge
route works on the M1 and M2 
 
 
 
 
 reduce_prod 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Decompose through log-sum-exp on host 
 
 
 
 
 
 The whole-tensor argument reductions global_argmax and
 global_argmin follow the same gate as reduce_argmin :
native on the intermediate-language route from the M3, reachable through
the bridge on the M1. 
 
 
 
 A.8 Data movement and
structural 

 
 Table   A.8 gives the data-movement and structural
operations, the largest class, spanning reshape, slice, gather, scatter,
and the space-channel set. 
 
 
 Table A.8: Data-movement and structural operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 reshape 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Metadata edit 
 
 
 
 
 reshape_like 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 expand_dims 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 squeeze 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 flatten2d 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 transpose 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Capped by the maximum transpose extent, 16384 through the M3, 65536 on
the M5 
 
 
 
 
 concat 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 DMA 
 
 
 
 
 split 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 stack 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 pad 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Constant pad is native everywhere; symmetric and reflect pad are
texture-gated, software on the M1 and native from the M2 
 
 
 
 
 slice_by_size 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 M1 and M2
nonzero width-offset routes through a fixed-point crop-DMA that
saturates a magnitude above 4094 to infinity; clean from the M3 
 
 
 
 
 slice_by_index 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Static-offset slice folds into the descriptor inside a graph 
 
 
 
 
 slice_update 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 reverse 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Measured on the M1 
 
 
 
 
 reverse_sequence 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose on host 
 
 
 
 
 tile 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Factors of 2, 3, 4, and 8 
 
 
 
 
 gather 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 M1 software path
valid only for a batch of one and a depth of one; the hardware path is
M2 onward 
 
 
 
 
 gather_along_axis 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Same M1 envelope caveat 
 
 
 
 
 gather_nd 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 M1 software
envelope only (batch one, depth one, three-element index channel);
native texture path from the M2 
 
 
 
 
 scatter 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose on host 
 
 
 
 
 scatter_along_axis 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose on host 
 
 
 
 
 scatter_nd 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Decompose on host 
 
 
 
 
 depth_to_space 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The
pixel-shuffle operation 
 
 
 
 
 space_to_depth 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The pixel-unshuffle operation 
 
 
 
 
 pixel_shuffle 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Engine-lane reorganization, factors of 2, 3, 4, and 8; z-factor must be
1 
 
 
 
 
 pixel_unshuffle 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Engine-lane reorganization; input dimension divisible by the
factor 
 
 
 
 
 space_to_batch 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Factor
in 2, 3, 4, 8; batch cap 4096 on older families, 65536 on the newer 
 
 
 
 
 batch_to_space 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Inverse of the above 
 
 
 
 
 identity 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Aliases a cast
or no-op 
 
 
 
 
 fill 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Constant tensor producer 
 
 
 
 
 fill_like 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Constant
tensor producer 
 
 
 
 
 range_1d 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 M1 code generation rejects it; host-precompute the constant 
 
 
 
 
 crop 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Slice and crop,
distinct from the texture crop-resize 
 
 
 
 
 band_part 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Mask on host 
 
 
 
 
 non_zero 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Data-dependent shape 
 
 
 
 
 one_hot 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Decompose through an identity gather on host 
 
 
 
 
 shape 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Static-shape
graphs only 
 
 
 
 
 sliding_windows 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose on host 
 
 
 
 
 
 
 A.9 Image, resize, and texture 

 
 Table   A.9 gives the image, resize, and texture
operations, gated to the texture engine from the A14 with software
fallbacks on the M1. 
 
 
 Table A.9: Image, resize, and texture operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 resize 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Texture-gated; M1
takes a software transpose fallback with different rounding, native from
the M2 
 
 
 
 
 resize_bilinear 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Software fallback on the M1 
 
 
 
 
 resize_nearest_neighbor 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Software fallback on the M1 
 
 
 
 
 upsample_bilinear 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Software fallback on the M1 
 
 
 
 
 upsample_nearest_neighbor 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Software fallback on the M1 
 
 
 
 
 crop_resize 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Texture engine, M2 onward; no host substitution wired 
 
 
 
 
 resample 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Texture
engine, M2 onward 
 
 
 
 
 affine 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Texture engine, M2 onward 
 
 
 
 
 pixel_buffer_to_tensor 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Four-character-code image input; an entitlement gate, not a chip gate 
 
 
 
 
 tensor_to_pixel_buffer 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Compiler-internal 
 
 
 
 
 gamma 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Image-signal
operation, compiler-internal 
 
 
 
 
 degamma 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Image-signal operation, compiler-internal 
 
 
 
 
 
 
 A.10 Quantization and dtype 

 
 Table   A.10 gives the quantization and dtype operations,
with the per-family streaming gates carried in the note column. 
 
 
 Table A.10: Quantization and dtype operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 cast 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 fp16 to fp32 and
bool native on the M1; cast to int32 is rejected on the M1 
 
 
 
 
 quantize 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Not texture-gated 
 
 
 
 
 dequantize 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 
 
 const 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Folded at compile, not a standalone code-generated operation 
 
 
 
 
 constexpr_affine_dequantize 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 int4 lookup-table streams from the M1; int8 and affine fold to
fp16 below the M2, and stream from the A14 and M2 
 
 
 
 
 constexpr_lut_to_dense 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Palette and lookup-table stream; int4 lookup-table
streams natively from the M1 
 
 
 
 
 constexpr_lut_to_sparse 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Folded constant; sparse stream from the M3 
 
 
 
 
 constexpr_blockwise_shift_scale 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Blockwise stream from the M3; folds to fp16
on the M1 and M2 
 
 
 
 
 constexpr_sparse_blockwise_shift_scale 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Sparse and blockwise stream from the M3 
 
 
 
 
 constexpr_sparse_to_dense 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Sparse streams natively from the M1 
 
 
 
 
 constexpr_cast 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Rejected on every family 
 
 
 
 
 
 
 A.11 Attention, control flow, and
state 

 
 Table   A.11 gives the attention, control-flow, and
state operations, where the state pair is native and the control-flow
operations are compiler-internal. 
 
 
 Table A.11: Attention, control-flow, and state operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 read_state 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Stateful;
needs the inout tensor-descriptor plumbing for a key-value cache 
 
 
 
 
 write_state 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Stateful 
 
 
 
 
 tensor_buffer_to_tensor 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Ring and streaming buffer mover, reachable inside a stateful graph 
 
 
 
 
 tensor_to_tensor_buffer 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Compiler-internal 
 
 
 
 
 circular_buffer_to_tensor 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Ring-buffer reader 
 
 
 
 
 tensor_to_circular_buffer 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Ring-buffer writer 
 
 
 
 
 cond 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 No standalone code
generation; flatten on host 
 
 
 
 
 while_loop 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 No standalone code generation; unroll on host 
 
 
 
 
 call 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Inlined 
 
 
 
 
 
 
 A.12 Recurrent cells 

 
 Table   A.12 gives the recurrent-cell operations, none of
which take an engine path; each unrolls on the host. 
 
 
 Table A.12: Recurrent-cell operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 gru 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Unroll to a
convolution, matmul, and activation graph on host 
 
 
 
 
 lstm 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Unroll on host 
 
 
 
 
 rnn 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Unroll on host 
 
 
 
 
 
 
 A.13 Trigonometric, special, and
math 

 
 Table   A.13 gives the trigonometric, special, and math
operations, where sin and cos go native from the M3
and atan is the one M1-native primitive. 
 
 
 Table A.13: Trigonometric, special, and math operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 sin 
 
 
 
 Family-gated 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native
from the M3; the M1 and M2 use a host polynomial 
 
 
 
 
 cos 
 
 
 
 Family-gated 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native from the M3; the M1 and M2 use a host polynomial 
 
 
 
 
 atan 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 The one
trigonometric primitive native on the M1 
 
 
 
 
 tan 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Decompose through a sin and cos identity on host 
 
 
 
 
 asin 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host
decomposition 
 
 
 
 
 acos 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host decomposition 
 
 
 
 
 atanh 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host
decomposition 
 
 
 
 
 asinh 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host decomposition 
 
 
 
 
 acosh 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host
decomposition 
 
 
 
 
 sinh 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host decomposition 
 
 
 
 
 cosh 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host
decomposition 
 
 
 
 
 cross_product 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Reachable through the bridge route, measured on the M1 
 
 
 
 
 cost_volume 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Reachable
through the bridge route, measured on the M1 
 
 
 
 
 matrix_decomposition 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 No observed code generation 
 
 
 
 
 
 
 A.14 Detection and sampling 

 
 Table   A.14 gives the detection and sampling
operations, the rank and sort bridge gated to the M2 and the random and
tensor-list operations off-engine. 
 
 
 Table A.14: Detection and sampling operations by device
family. 
 
 
 
 
 
 Operation 
 
 
 
 M1 (A13) 
 
 
 
 M2 (A14) 
 
 
 
 M3 (A15) 
 
 
 
 M4, M5 (A16, A17) 
 
 
 
 Note 
 
 
 
 
 
 
 non_maximum_suppression 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Reachable only with a CPU or GPU backend in the mask; the engine-only
mask reports not supported on any backend, so it offloads to the CPU or
GPU rather than the engine 
 
 
 
 
 topk 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Rank and sort bridge, M2 onward; the validator is callable on the M1
but code generation rejects it 
 
 
 
 
 argsort 
 
 
 
 Family-gated 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Sort
family, M2 onward; code-generation-rejected on the M1 
 
 
 
 
 random_uniform 
 
 
 
 Bridge 
 
 
 
 Bridge 
 
 
 
 Native 
 
 
 
 Native 
 
 
 
 Hardware generator from the M3; host random below it 
 
 
 
 
 random_bernoulli 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host random 
 
 
 
 
 random_categorical 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 No path 
 
 
 
 Host random 
 
 
 
 
 random_normal 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Host
random 
 
 
 
 
 list_gather 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Tensor-list operation 
 
 
 
 
 list_length 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Tensor-list operation 
 
 
 
 
 list_read 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Tensor-list operation 
 
 
 
 
 list_scatter 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Tensor-list operation 
 
 
 
 
 list_write 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No
path 
 
 
 
 Tensor-list operation 
 
 
 
 
 make_list 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 No path 
 
 
 
 Tensor-list operation 
 
 
 
 
 
 
 
 Appendix B Hidden-layer catalog 

 
 
 SUMMARY 
 This appendix is the reference catalog of the hardware-native layer
kinds reached by authoring the network description directly, behind
chapter 26 . 
 
 
 
 Every row is a native descriptor the conversion path never emits: the
descriptor and its
 _ANECValidate<Name>Layer checker are
present in the compiler on every target, and the layer is reached by
handing the compiler a Unit whose Type is the native name and
whose Params hold the attributes the matching
 ZinParse<Name>Unit parser reads. 
 
 
 B.1 Catalog 

 
 Table   B.1 lists each native layer kind with what it
computes, its netplist Type and compiler symbol, and its family
gate. 
 
 
 Table B.1: The hidden-layer
catalog. 
 
 
 
 
 
 Layer kind 
 
 
 
 What it computes 
 
 
 
 Netplist Type and compiler symbol 
 
 
 
 Family gate 
 
 
 
 
 
 
 Fused attention 
 
 
 
 softmax ⁡ ( Q ​ K ⊤ ⋅ s + M ) ​ V \mathrm{softmax}(QK^{\top}\cdot s+M)\,V from
four operands (Q, K, V, scale) plus an optional fifth additive mask
 M M , with the channel axis holding the sequence 
 
 
 
 SDPA ;
 ANECSDPALayerDesc , ZinParseSDPAUnit ,
 anec.sdpa . The one parsed key is SubtractMax ,
defaulting false in _ANECSDPALayerDescInitialize and set true
for a correct softmax 
 
 
 
 All families from the M1 onward; runs on the
matmul, softmax, and transpose path, not the texture engine 
 
 
 
 
 Sort 
 
 
 
 Full sort along a chosen axis, ascending or
descending, values or argsort indices 
 
 
 
 Sort ;
 ZinParseSortUnit . Keys: Direction ,
 SortDimension , VectorDimension , SortIndices ,
 Indices 
 
 
 
 Validator callable on the M1, but the code generator
rejects Sort there; runs on later families 
 
 
 
 
 Top-k 
 
 
 
 The k largest or smallest along an axis, values or indices,
index outputs returned float16-encoded and exact below 2048 
 
 
 
 TopK ; ZinParseTopKUnit . Keys: Type (Max or
Min), K , SortDimension , VectorDimension ,
 SortIndices , Indices 
 
 
 
 Runs on the M1 outside a
forbidden band: K in { 3 , 4 } \{3,4\} fails the compiler at every
width 
 
 
 
 
 Argument min and max 
 
 
 
 Spatial or channel argmin and
argmax over a kernel window 
 
 
 
 ArgMinMax ;
 _ANECValidateArgMinMaxLayer . Keys: Mode 
(SpatialArgMax, ChannelArgMax, SpatialArgMin, ChannelArgMin),
 KernelWidth , KernelHeight , Pad* 
 
 
 
 All
families from the M1 onward 
 
 
 
 
 Whole-tensor argument min and max 
 
 
 
 Argmin or argmax over an entire
tensor dimension 
 
 
 
 GlobalArgMinMax . Keys: Type (Max or
Min), Dimension 
 
 
 
 Gated to the A15 generation; rejected on the
M1 
 
 
 
 
 Spatial rearrange 
 
 
 
 Depth-to-space and space-to-depth in
two channel-ordering conventions, plus space-and-batch reshuffles,
parameterized by per-axis integer factors 
 
 
 
 PixelShuffle ,
 PixelUnshuffle , ChannelToSpace ,
 SpaceToChannel , SpaceToBatch , BatchToSpace ;
 ZinParse<Name>Unit . Three int32 keys:
 FactorX , FactorY , FactorZ 
 
 
 
 All families from
the M1 onward; BatchToSpace requires batch N N divisible by
 FactorX times FactorY 
 
 
 
 
 Range normalization 
 
 
 
 Maps a tensor to its minimum-to-maximum span per
row or per column 
 
 
 
 MinMaxNormalization ;
 _ANECValidateMinMaxNormLayer ,
 _ANECMinMaxNormLayerDescInitialize . Keys: Dimension 
(Width or Height), Epsilon as a float16 bit pattern 
 
 
 
 Width and
Height run; Dimension of Channel is arch-gated and rejected on
the M1 
 
 
 
 
 Local response normalization 
 
 
 
 Cross-channel response
normalization over a channel window 
 
 
 
 LocalResponseNormalization ; _ANECValidateLRNLayer .
 Alpha is a float16 bit pattern divided internally by
 KernelChannel ; only the first KernelChannel channels
are normalized 
 
 
 
 All families from the M1 onward 
 
 
 
 
 Scaled elementwise 
 
 
 
 A binary elementwise op fused with a scalar scale,
 y = s ⁡ ( x op z ) y=s\,(x\mathbin{\mathrm{op}}z) 
 
 
 
 ScaledElementWise .
Keys: Type (Add, Mult, Sub, and the elementwise vocabulary),
 Scale as a float16 bit pattern 
 
 
 
 All families from the M1
onward 
 
 
 
 
 Template cross-correlation 
 
 
 
 Valid cross-correlation of
a single-channel map with an unflipped template,
 y ⁡ [ i , j ] = ∑ u , v x ⁡ [ i + u , j + v ] ​ t ​ [ u , v ] y[i,j]=\sum_{u,v}x[i+u,j+v]\,t[u,v] 
 
 
 
 CrossCorrelation .
The MIL frontend rejects the op; the netplist Type reaches it
directly 
 
 
 
 All families from the M1 onward 
 
 
 
 
 Three-vector cross product 
 
 
 
 The cross product of two length-3 vectors
held in the channel axis, cross ⁡ ( x , z ) \mathrm{cross}(x,z) 
 
 
 
 CrossProduct . Inputs shaped D1 C3 H1 W1; the MIL frontend
rejects the op 
 
 
 
 All families from the M1 onward 
 
 
 
 
 Furthest-point sampling 
 
 
 
 Greedy L2 furthest-point
sampling of up to 1024 centroids from up to 8192 points, seeded at the
first point, centroids returned channel-major 
 
 
 
 FurthestPointSampling . Keys: CentroidCount ,
 DistanceMetric (L2 only on this architecture) 
 
 
 
 All families
from the M1 onward 
 
 
 
 
 Radius neighborhood search 
 
 
 
 An L2 ball query returning a
points-by-centroids membership matrix, one membership flag per pair 
 
 
 
 RadiusSearch . Two inputs (centroids, points), both D1 C3 H1;
key Radius 
 
 
 
 All families from the M1 onward 
 
 
 
 
 Stereo cost volume 
 
 
 
 The L1 matching cost per disparity,
 cost ⁡ [ d , x ] = | aux ⁡ [ x ] − ref ⁡ [ x + d ] | \mathrm{cost}[d,x]=\lvert\mathrm{aux}[x]-\mathrm{ref}[x+d]\rvert ,
over R + 1 R+1 disparity planes 
 
 
 
 CostVolume . Keys:
 DisparityDirection , DisparityRange ; requires reference
width W r ≥ W a + R W_{r}\geq W_{a}+R 
 
 
 
 All families from the M1 onward 
 
 
 
 
 Re-strided input view 
 
 
 
 A contiguous offset window
 x [ Offset : Offset + Size ] x[\text{Offset}:\text{Offset}+\text{Size}] along one named axis,
no data movement 
 
 
 
 InputView . Keys: Dimension ,
 Offset , Size , Step ; gates
 InvalidInputView{Dimension,Offset,Size,Step} 
 
 
 
 All families
from the M1 onward 
 
 
 
 
 Runtime-offset dynamic slice 
 
 
 
 A window
 x [ start : start + SliceSize ] x[\text{start}:\text{start}+\text{SliceSize}] whose start is
bound as a constant or runtime index 
 
 
 
 DynamicSlice ; reached by
the MIL slice_by_index path. Keys:
 DynamicSliceAxisOrder , DynamicSliceInfo ,
 CoordinateInfo , PaddingInfo , BackgroundValue 
 
 
 
 Validator callable on the M1, but the code generator rejects
 DynamicSlice there; runs on later families 
 
 
 
 
 Tile, concatenate, and reshape utilities 
 
 
 
 Flatten as an NCHW identity
reshape, inference-time dropout as identity, and broadcast of a length-1
axis 
 
 
 
 Flatten , Dropout (rate 0), Broadcast 
(keys Dimension , Size ) 
 
 
 
 All families from the M1
onward 
 
 
 
 
 
 
 B.2 Arch-gated negatives 

 
 Three rows above name layers a later chip accepts and the M1 rejects, by
the family gates of chapter 12 .
 GlobalArgMinMax is gated to the A15 generation and rejected on
the M1. MinMaxNormalization with a Channel reduction is
arch-gated and rejected on the M1, while its Width and Height reductions
run. The texture-engine samplers (resize, crop-and-resize, grid
resample, and the affine spatial transform) are accepted from the A14
generation and rejected on the M1, where the compiler reports that the
affine transform is not supported on this architecture. They are part of
the same gated family but are not authored as netplist Units here. 
 
 
 A second class of rejection is not a family gate but the
attested-is-not-reachable rule of chapter
 4 : the Sort and
 DynamicSlice validators are callable on the M1, yet the code
generator rejects both, and TopK is accepted only outside the
 { 3 , 4 } \{3,4\} band. An authored layer is confirmed by a compile-and-run
on the target, not by the presence of its descriptor. 
 
 
 
 B.3 Validator gate set 

 
 Every authored layer passes through one per-layer validator, the
 _ANECValidate<Op>Layer family, of which
55 symbols are exported and 50 are per-layer. The compiler runs the same
validators in two roles: the segmenter dry-runs them through
 _ANECValidateNetworkCreate to decide engine eligibility, and
the back-end legalizer re-runs them during a real compile, so the
dry-run prediction never drifts from the compile result. The five
non-layer exports are _ANECValidate ,
 _ANECValidateNetworkCreate , _ANECValidateMPSModule ,
 _ANECValidateMPSModuleCreate , and
 _ANECValidateMutableProcedureInfo . 
 
 
 Each validator reads a fixed bottom (input-tensor) count and a per-chip
feature byte from the hardware-abstraction layer, and rejects with a
measured literal string. Table   B.2 reproduces those
gates for the validators that guard the authored and bridge-reachable
layers, with the bottom count, constraint, and reject string for each. 
 
 
 Table B.2: The per-layer validator
gates. 
 
 
 
 
 
 Validator 
 
 
 
 Bottoms 
 
 
 
 Gate and constraint 
 
 
 
 Reject string 
 
 
 
 
 
 
 SDPA 
 
 
 
 4 or 5 
 
 
 
 key and value same shape; mask
broadcast-compatible; scale constant 
 
 
 
 SDPA layer must have only 4 or 5(optional mask) inputs 
 
 
 
 
 Conv 
 
 
 
 1 plus weight 
 
 
 
 kernel within the
per-chip range; large kernel W and H multiple of 8; channels divisible
by groups 
 
 
 
 Invalid conv kernel %s = %zd, It should be in [%zd, %zd] 
 
 
 
 
 MatrixMult 
 
 
 
 2 
 
 
 
 depth 1 on both operands; out-C equals A-C;
fits the kernel-memory budget 
 
 
 
 depth > 1 is not supported for MatMult 
 
 
 
 
 Linear 
 
 
 
 1 plus weight 
 
 
 
 input rank below 5 
 
 
 
 Linear layer must have only one single input. 
 
 
 
 
 Pool 
 
 
 
 1 
 
 
 
 window below input; pad below kernel; mode gated per
chip 
 
 
 
 Pooling mode "%s" is not available on this ANE architecture. 
 
 
 
 
 Neuron 
 
 
 
 1 
 
 
 
 non-linear mode 1 to 46; type in
the per-chip list; ReLU-N positive parameters when the gate byte is 0 
 
 
 
 This platform doesn't support Neuron %s 
 
 
 
 
 Reduction 
 
 
 
 1 
 
 
 
 reduce-then-square needs feature byte
 0x494 (0 through the M1); each axis at most 4 
 
 
 
 square operation after reduction is not supported 
 
 
 
 
 Softmax 
 
 
 
 1 
 
 
 
 feature byte 0x815 (0 on
older); output Float 
 
 
 
 Softmax is not supported by this ANE architecture 
 
 
 
 
 LayerNorm 
 
 
 
 1 
 
 
 
 channels divisible by num-groups; grouped form
requires depth 1 
 
 
 
 ... does not yet support depth > 1 
 
 
 
 
 InstanceNorm 
 
 
 
 1 
 
 
 
 feature byte 0x816 ;
spatial axes only 
 
 
 
 InstanceNorm layer not supported for this ANE architecture 
 
 
 
 
 MinMaxNorm 
 
 
 
 1 
 
 
 
 feature byte 0x818 ; spatial only, the
Channel axis arch-gated 
 
 
 
 (encoded assert, byte 0x818 ) 
 
 
 
 
 LRN 
 
 
 
 1 
 
 
 
 feature byte 0x81a ; channel
count of 16 or above fails code generation on the M1 
 
 
 
 LRN is not supported on this architecture. 
 
 
 
 
 ArgMinMax 
 
 
 
 1 
 
 
 
 channel-reduce C at most 2048 fp16; pad below
kernel; equal left and right, zero front and back 
 
 
 
 ArgMinMax layer must have one input 
 
 
 
 
 GlobalArgMinMax 
 
 
 
 1 
 
 
 
 feature byte
 0x4f2 (1 from the M1 on the bridge route); mode 1 or 2; reduce
dimension not 5 
 
 
 
 (encoded assert, byte 0x4f2 ) 
 
 
 
 
 Transpose 
 
 
 
 1 
 
 
 
 permutation valid; extent capped 16384 through
the M3, 65536 on the M5; last four dimensions only 
 
 
 
 NE Input Transpose is not supported for this arch 
 
 
 
 
 Concat 
 
 
 
 variadic 
 
 
 
 match input zero on every
non-concat axis; constant positive axis; same layout 
 
 
 
 Concat layer must have at least 2 inputs 
 
 
 
 
 Pad 
 
 
 
 1 
 
 
 
 H or W axes only; symmetric and reflect modes need
texture byte 0x81d (0 on the M1) 
 
 
 
 Channel padding is not supported on ANE 
 
 
 
 
 Broadcast 
 
 
 
 1 
 
 
 
 broadcast only from a length-1
axis; depth-axis broadcast needs byte 0x812 
 
 
 
 Broadcast along depth axis is not supported on this architecture 
 
 
 
 
 Gather 
 
 
 
 2 
 
 
 
 M1 software envelope: data batch 1, depth 1, index
channel 3; texture path from the A14 
 
 
 
 Cannot decompose layer on this architecture 
 
 
 
 
 PixelShuffle / PixelUnshuffle 
 
 
 
 1 
 
 
 
 depth factor 1; W and H factors in 1, 2, 3, 4, 8; channel divisible by
the factor product 
 
 
 
 returned invalid: 
 
 
 
 
 SpaceToBatch / BatchToSpace 
 
 
 
 1 
 
 
 
 factors fully factor
into 2, 3, 4, 8; batch divisible by the factor product 
 
 
 
 Input batch n = %zd is not divisible by factor x = %d * factor y = %d 
 
 
 
 
 ChannelToSpace 
 
 
 
 1 
 
 
 
 the z dimension is not
reorganizable 
 
 
 
 ChannelToSpace in z dimension is not supported, current factor.z = %d. 
 
 
 
 
 Resize 
 
 
 
 1 
 
 
 
 dimension or ratio, not both; sampling axes H and
W; texture byte 0x81d (0 on the M1 takes a software route) 
 
 
 
 failed to map resize layer on this arch 
 
 
 
 
 CropResize 
 
 
 
 2 
 
 
 
 index format fp16; texture
engine from the A14; same coordinate, method, and padding across axes 
 
 
 
 Codegen Error: Invalid Texture CropCfg 
 
 
 
 
 AffineTransform 
 
 
 
 2 
 
 
 
 matrix fp16; texture byte 0x81d 
(0 on the M1) 
 
 
 
 affine transform is not supported on this architecture 
 
 
 
 
 Resample 
 
 
 
 2 
 
 
 
 warp depth 1; warp channel 1 or
2; texture engine from the A14 
 
 
 
 Channel size in coordinates should be 1 or 2 
 
 
 
 
 Sort 
 
 
 
 1 
 
 
 
 direction valid; output fp16 or uint16; validator
passes, code generation rejects on the M1 
 
 
 
 (passes validation,
code-generation reject) 
 
 
 
 
 TopK 
 
 
 
 1 
 
 
 
 k in the sort-dimension range; the
M1 rejects at code generation, and k in 3 or 4 is forbidden on the M5 
 
 
 
 (passes validation, code-generation reject) 
 
 
 
 
 Dropout 
 
 
 
 1 
 
 
 
 feature byte 0x4a9 (1 only from the
A15); rate in the half-open unit interval 
 
 
 
 Dropout layer is not supported on this architecture. 
 
 
 
 
 Random 
 
 
 
 none 
 
 
 
 feature byte 0x4a9 (1
only from the A15); low below high; output Int8, UInt8, or Float16 
 
 
 
 Random layer is not supported on this architecture. 
 
 
 
 
 RingBufferWriter 
 
 
 
 2 
 
 
 
 the writer must connect to a live-state
buffer; circular mode arch-gated 
 
 
 
 Circular buffer is not supported on this architecture 
 
 
 
 
 NMS 
 
 
 
 2 or more 
 
 
 
 boxes channel 4; runs only on
a CPU or GPU backend, never engine-native 
 
 
 
 (passes validation, not
engine-native) 
 
 
 
 
 
 The validators are public exported symbols, so they are callable from
user space, and this is the basis of the precompile predictor: a
callable validator marks a schema-gated layer reachable by direct
authoring. A callable validator that accepts the schema does not
guarantee the layer compiles, which is why the Sort ,
 TopK , DynamicSlice , and the M1 CropResize 
rows pass the validator and fail at hardware-executable lowering. One
opcode-surface gap holds the other way: the RCAS and Reverse operations
have an internal semantics validator but no exported per-layer symbol,
so they are not reachable by direct authoring through this route. 
 
 
 
 
 Appendix C Decoded reference tables 

 
 
 SUMMARY 
 This appendix collects the decoded values cited throughout the guide
into one reference: enum tokens, struct layouts, status codes, the
register-init table, command table, register map, and program-container
schema. Each section begins with its table and names the research-corpus
file that contains the full set when only a representative excerpt is
reproduced here. 
 
 
 
 Each section reproduces the representative and structurally important
rows of a larger table. Where a table runs to hundreds or thousands of
rows, the full set is in the research corpus and the section names the
file that contains it. Every value here is read out of an M1/H13 binary
by static analysis. 
 
 
 C.1 Operation-attribute enum tokens to integer
values 

 
 These are the integer codes the compiler resolves attribute string
tokens to. Table   C.1 is the front-end activation
token map ( MILOpConverter::NeuronTypeFromString , 33 entries,
miss resolves to 0). 
 
 
 Table C.1: The front-end activation token names and the integer neuron
codes they resolve to. 
 
 
 
 token 
 int 
 token 
 int 
 
 
 
 relu 
 1 
 gelu 
 23 
 
 leaky_relu 
 2 
 degamma 
 25 
 
 clamped_relu 
 3 
 trunc 
 26 
 
 relu_n (relu6) 
 4 
 round_nearest 
 27 
 
 sigmoid 
 5 
 floor 
 28 
 
 sigmoid_high_precision 
 6 
 ceil 
 29 
 
 tanh 
 7 
 erf 
 31 
 
 silu (alias swish ) 
 9 
 threshold_relu 
 32 
 
 swish_hard 
 10 
 gamma 
 33 
 
 sqr 
 11 
 inv 
 14 
 
 sqrt 
 12 
 log2 
 15 
 
 rsqrt 
 13 
 exp2 
 16 
 
 elu 
 18 
 exp 
 17 
 
 sin 
 20 
 sign 
 19 
 
 cos 
 21 
 sigmoid_hard 
 22 
 
 
 
 
 The serialization dtype enum ( ANECIRDataType , the
 dtype / storage_type attribute) is an 11-code space,
given as table   C.2 . 
 
 
 Table C.2: The serialization data-type codes and the element types they
name. 
 
 
 
 int 
 type 
 int 
 type 
 
 
 
 0 
 int4 
 6 
 uint16 
 
 1 
 uint8 
 7 
 int32 
 
 2 
 int8 
 8 
 uint32 
 
 3 
 fp16 
 9 
 int64 
 
 4 
 fp32 
 10 
 uint64 
 
 5 
 int16 
 
 
 
 
 
 
 The MLIR symbolize* enums are a length-dispatched chain of
packed integer string compares, fully static, each miss resolving to 0,
collected in table   C.3 . 
 
 
 Table C.3: The symbolized attribute tokens and the integer values each one
maps to. 
 
 
 
 
 
 attribute 
 
 
 
 token 
 
 
 
 int 
 
 
 
 
 
 
 padding_style 
 
 
 
 EXPLICIT / TF_VALID /
 TF_SAME / EXPLICIT_OFFSET /
 ONNX_SAME_LOWER 
 
 
 
 0 / 1 / 2 / 3 / 4 
 
 
 
 
 nearest_rounding_mode 
 
 
 
 round_prefer_ceil / round_prefer_floor /
 ceil / floor / round_to_even /
 round_to_odd 
 
 
 
 0 / 1 / 2 / 3 / 4 / 5 
 
 
 
 
 reduce_op 
 
 
 
 min / max / sum /
 prod / argMin / argMax 
 
 
 
 0 / 1 / 2 / 3 / 4 /
5 
 
 
 
 
 data_layout 
 
 
 
 NCHW / NHWC /
 OIHW / HWIO / CHW / HWC /
 HW 
 
 
 
 0 / 1 / 2 / 3 / 4 / 5 / 6 
 
 
 
 
 data_layout 
 
 
 
 NCDHW / NDHWC / OIDHW 
/ DHWIO 
 
 
 
 7 / 8 / 9 / 10 
 
 
 
 
 scatter mode 
 
 
 
 add / subtract 
/ multiply / divide / min / max /
 set 
 
 
 
 0 / 1 / 2 / 3 / 4 / 5 / 6 
 
 
 
 
 pool indices_mode 
 
 
 
 GlobalFlatten1D .. 4D /
 LocalFlatten1D .. 4D 
 
 
 
 0..3 / 4..7 
 
 
 
 
 RNN gate activation 
 
 
 
 none / relu /
 tanh / sigmoid / hard_sigmoid /
 scaled_tanh 
 
 
 
 0 / 1 / 2 / 3 / 4 / 5 
 
 
 
 
 stencil padding_mode 
 
 
 
 constant / mirror /
 mirrorWithEdge / clampToEdge / zero /
 periodic / antiPeriodic 
 
 
 
 0 / 1 / 2 / 3 / 4 / 5 / 6 
 
 
 
 
 pixel_format 
 
 
 
 R8Unorm /
 RG8Unorm / RGBA8Unorm / BGRA8Unorm /
 R16Float 
 
 
 
 0 / 1 / 2 / 3 / 4 
 
 
 
 
 pixel_format 
 
 
 
 RG16Float / RGBA16Float /
 R32Float / RG32Float / RGBA32Float 
 
 
 
 5 / 6 /
7 / 8 / 9 
 
 
 
 
 arith::RoundingMode 
 
 
 
 to_nearest_even / downward / upward /
 toward_zero / to_nearest_away 
 
 
 
 0 / 1 / 2 / 3 /
4 
 
 
 
 
 collective reduction 
 
 
 
 sum / max / min /
 prod / mean 
 
 
 
 1 / 2 / 3 / 4 / 5 
 
 
 
 
 
 A second class of enum is in a packed pointer table in the data segment,
the internal Zin enums the lowering layer dispatches on, listed
in table   C.4 . 
 
 
 Table C.4: The internal Zin enum value-to-token maps the
lowering layer dispatches on. 
 
 
 
 
 
 enum 
 
 
 
 value to token 
 
 
 
 
 
 
 ZinIrPoolingType 
 
 
 
 1 Avg, 2 Max, 3 ChannelMax, 4 Min, 5
ChannelMin, 6 L1, 7 L2, 8 SpatialAndChannelAvg, 9 SpatialAndChannelMax,
10 SpatialAndChannelMin, 11 SpatialArgMax, 12 ChannelArgMax, 13
SpatialArgMin, 14 ChannelArgMin 
 
 
 
 
 ZinIrReductionType 
 
 
 
 0 Sum, 1 Min, 2 Max, 3
Avg, 4 SatSum, 5 SatSub, 6 ArgMin, 7 ArgMax, 8 BitwiseAnd, 9 BitwiseOr,
10 BitwiseXor 
 
 
 
 
 ZinIrEWType 
 
 
 
 1 Add, 2 Mult, 3 Square, 4 Sub, 5 Power, 6 Div, 7
Max, 8 Min, 9 Abs, 10 EqualZero, 11 NotEqualZero, 12 LessThanZero, 13
LessThanEqualZero, 14 GreaterThanEqualZero, 15 GreaterThanZero, 16
Equal, 17 NotEqual, 18 LessThan, 19 LessThanEqual, 20 GreaterThanEqual,
21 GreaterThan 
 
 
 
 
 ZinIrScaledEWType 
 
 
 
 1 Add, 2 Mult, 3 SumSquare,
4 Max, 5 Min 
 
 
 
 
 ZinIrPaddingMode 
 
 
 
 1 Zero, 2 Negative, 3 Replication, 5
Symmetric, 6 Reflective, 7 Background, 8 DontCare 
 
 
 
 
 ZinIrSamplingMethod 
 
 
 
 0 Linear, 1
NearestNeighbor 
 
 
 
 
 ZinIrSamplingGridMode 
 
 
 
 0 AlignedCorners, 1 UnalignedCorners, 2
OffsetCorners, 3 Default, 4 OffsetDefault, 5
OffsetDefaultWithNominalScale, 6 StrictAlignedCorners 
 
 
 
 
 ZinIrCoordinateMode 
 
 
 
 0 NonNormalized, 1
NormalizedSymmetric, 2 NormalizedReflect 
 
 
 
 
 ZinArgMode 
 
 
 
 1 SpatialArgMin, 2 ChannelArgMin, 3 SpatialArgMax,
4 ChannelArgMax 
 
 
 
 
 ZinIrSortDirection 
 
 
 
 0 Invalid, 1 Ascending, 2
Descending 
 
 
 
 
 ZinIrTopKType 
 
 
 
 0 Invalid, 1 Min, 2 Max 
 
 
 
 
 ZinIrFlattenType 
 
 
 
 1 NCHW, 2 NHWC 
 
 
 
 
 ZinIrDimension 
 
 
 
 0 N, 1 D, 2 C, 3 H, 4 W 
 
 
 
 
 
 The op-class selector is the ZinUnitType table, 79 entries, the
engine-unit each layer routes to, given in full as
 table   C.5 . 
 
 
 Table C.5: The complete 79-entry ZinUnitType op-class
table and the engine unit each value
selects. 
 
 
 
 int 
 unit 
 int 
 unit 
 int 
 unit 
 
 
 
 1 
 Conv 
 28 
 LayerNormalization 
 55 
 RandomGenerator 
 
 2 
 Pooling 
 29 
 LocalResponseNormalization 
 56 
 Alias 
 
 3 
 Concat 
 30 
 CostVolume 
 57 
 CrossProduct 
 
 4 
 ElementWise 
 31 
 PixelShuffle 
 58 
 Quant 
 
 5 
 ScaledElementWise 
 32 
 PixelUnshuffle 
 59 
 DeQuant 
 
 6 
 Neuron 
 33 
 FurthestPointSampling 
 60 
 Linear 
 
 7 
 NeuronCustom 
 34 
 SpaceToBatch 
 61 
 RingBufferWriter 
 
 8 
 GOC 
 35 
 BatchToSpace 
 62 
 RingBufferReader 
 
 9 
 DynamicGOC 
 36 
 SpaceToChannel 
 63 
 BatchNorm 
 
 10 
 ConstMatrixMatrixMult 
 37 
 ChannelToSpace 
 64 
 Phi 
 
 11 
 Flatten 
 38 
 RadiusSearch 
 65 
 Condition 
 
 12 
 Unflatten 
 39 
 Gather 
 66 
 WaitForEvent 
 
 13 
 CrossCorrelation 
 40 
 AffineTransform 
 67 
 SignalEvent 
 
 14 
 KernelRasterizer 
 41 
 Resize 
 68 
 NEConv 
 
 15 
 ArgMinMax 
 42 
 ResizeAs 
 69 
 NEMatMul 
 
 16 
 GlobalArgMinMax 
 43 
 Resample 
 70 
 NEPool 
 
 17 
 InputView 
 44 
 Padding 
 71 
 NEBypass 
 
 18 
 MatrixMultiplication 
 45 
 Tile 
 72 
 PEPool 
 
 19 
 Broadcast 
 46 
 CropResize 
 73 
 PEElementWise 
 
 20 
 Reduction 
 47 
 DynamicSlice 
 74 
 PEGOC 
 
 21 
 Transpose 
 48 
 PlaneReader 
 75 
 AllSlice 
 
 22 
 Reshape 
 49 
 PlaneWriter 
 76 
 AllGather 
 
 23 
 Shape 
 50 
 Sort 
 77 
 SDPA 
 
 24 
 Softmax 
 51 
 TopK 
 78 
 AllReduce 
 
 25 
 InstanceNormalization 
 52 
 NMS 
 79 
 FunctionCall 
 
 26 
 L2Normalization 
 53 
 MatrixDecomposition 
 
 
 
 27 
 MinMaxNormalization 
 54 
 Dropout 
 
 
 
 
 
 
 The activation non-linear-mode space is a parallel table,
 NonLinearModeToString , 48 slots indexed directly by the lower
hardware mode value, reproduced as table   C.6 . 
 
 
 Table C.6: The complete 48-slot NonLinearModeToString 
table indexed by hardware non-linear-mode
value. 
 
 
 
 
 
 idx 
 
 
 
 mode 
 
 
 
 idx 
 
 
 
 mode 
 
 
 
 idx 
 
 
 
 mode 
 
 
 
 
 
 
 0 
 
 
 
 none 
 
 
 
 16 
 
 
 
 rsqrt 
 
 
 
 32 
 
 
 
 sin 
 
 
 
 
 1 
 
 
 
 relu 
 
 
 
 17 
 
 
 
 clamped_relu_rsqrt 
 
 
 
 33 
 
 
 
 cos 
 
 
 
 
 2 
 
 
 
 sigmoid 
 
 
 
 18 
 
 
 
 inv 
 
 
 
 34 
 
 
 
 gelu 
 
 
 
 
 3 
 
 
 
 sigmoid_high_precision 
 
 
 
 19 
 
 
 
 sqr 
 
 
 
 35 
 
 
 
 gelu_sigmoid_approximation 
 
 
 
 
 4 
 
 
 
 relu_sigmoid 
 
 
 
 20 
 
 
 
 log2 
 
 
 
 36 
 
 
 
 degamma 
 
 
 
 
 5 
 
 
 
 sigmoid_hard 
 
 
 
 21 
 
 
 
 exp2 
 
 
 
 37 
 
 
 
 round_nearest 
 
 
 
 
 6 
 
 
 
 tanh 
 
 
 
 22 
 
 
 
 exp 
 
 
 
 38 
 
 
 
 trunc 
 
 
 
 
 7 
 
 
 
 clamped_relu 
 
 
 
 23 
 
 
 
 elu 
 
 
 
 39 
 
 
 
 floor 
 
 
 
 
 8 
 
 
 
 prelu 
 
 
 
 24 
 
 
 
 sign 
 
 
 
 40 
 
 
 
 ceil 
 
 
 
 
 9 
 
 
 
 relun 
 
 
 
 25 
 
 
 
 equal_zero 
 
 
 
 41 
 
 
 
 atan 
 
 
 
 
 10 
 
 
 
 swish 
 
 
 
 26 
 
 
 
 not_equal_zero 
 
 
 
 42 
 
 
 
 atan_part1 
 
 
 
 
 11 
 
 
 
 swish_hard 
 
 
 
 27 
 
 
 
 less_than_zero 
 
 
 
 43 
 
 
 
 atan_part2 
 
 
 
 
 12 
 
 
 
 dirac 
 
 
 
 28 
 
 
 
 less_than_equal_zero 
 
 
 
 44 
 
 
 
 erf 
 
 
 
 
 13 
 
 
 
 int 
 
 
 
 29 
 
 
 
 greater_than_equal_zero 
 
 
 
 45 
 
 
 
 thresholded_relu 
 
 
 
 
 14 
 
 
 
 frac 
 
 
 
 30 
 
 
 
 greater_than_zero 
 
 
 
 46 
 
 
 
 gamma 
 
 
 
 
 15 
 
 
 
 sqrt 
 
 
 
 31 
 
 
 
 custom_lut 
 
 
 
 47 
 
 
 
 abs 
 
 
 
 
 
 The micro-op opcode space ( ZinIrOpLayerOpCodeType , 126 codes,
 0x00 .. 0x7d ) has the codes the task-descriptor builder
dispatches on, given in full as table   C.7 . 
 
 
 Table C.7: The complete 126-entry micro-operation opcode table and the
layer-kind name each value dispatches
on. 
 
 
 
 
 
 op 
 
 
 
 dec 
 
 
 
 string 
 
 
 
 op 
 
 
 
 dec 
 
 
 
 string 
 
 
 
 
 
 
 0x00 
 
 
 
 0 
 
 
 
 CONV 
 
 
 
 0x3f 
 
 
 
 63 
 
 
 
 AFFINE_TRANFORM 
 
 
 
 
 0x01 
 
 
 
 1 
 
 
 
 POOL 
 
 
 
 0x40 
 
 
 
 64 
 
 
 
 PLANE_READER 
 
 
 
 
 0x02 
 
 
 
 2 
 
 
 
 SCALE_BIAS 
 
 
 
 0x41 
 
 
 
 65 
 
 
 
 PLANE_WRITER 
 
 
 
 
 0x03 
 
 
 
 3 
 
 
 
 TERNARY_DYNAMIC_GOC 
 
 
 
 0x42 
 
 
 
 66 
 
 
 
 SORT 
 
 
 
 
 0x04 
 
 
 
 4 
 
 
 
 ACTIVATION 
 
 
 
 0x43 
 
 
 
 67 
 
 
 
 TOP_K 
 
 
 
 
 0x05 
 
 
 
 5 
 
 
 
 EW 
 
 
 
 0x44 
 
 
 
 68 
 
 
 
 RCAS 
 
 
 
 
 0x06 
 
 
 
 6 
 
 
 
 SCALED_EW 
 
 
 
 0x45 
 
 
 
 69 
 
 
 
 INDEX 
 
 
 
 
 0x07 
 
 
 
 7 
 
 
 
 CONCAT 
 
 
 
 0x46 
 
 
 
 70 
 
 
 
 NMS 
 
 
 
 
 0x08 
 
 
 
 8 
 
 
 
 SPLIT 
 
 
 
 0x47 
 
 
 
 71 
 
 
 
 DROPOUT 
 
 
 
 
 0x09 
 
 
 
 9 
 
 
 
 COPY 
 
 
 
 0x48 
 
 
 
 72 
 
 
 
 TYPE_CAST 
 
 
 
 
 0x0a 
 
 
 
 10 
 
 
 
 FLATTEN 
 
 
 
 0x49 
 
 
 
 73 
 
 
 
 STOCHASTIC_ROUND 
 
 
 
 
 0x0b 
 
 
 
 11 
 
 
 
 UNFLATTEN 
 
 
 
 0x4a 
 
 
 
 74 
 
 
 
 RANDOM_GENERATOR 
 
 
 
 
 0x0c 
 
 
 
 12 
 
 
 
 CROSS_CORRELATION 
 
 
 
 0x4b 
 
 
 
 75 
 
 
 
 LINEAR 
 
 
 
 
 0x0d 
 
 
 
 13 
 
 
 
 CROSS_PRODUCT 
 
 
 
 0x4c 
 
 
 
 76 
 
 
 
 RINGBUFFER_WRITER 
 
 
 
 
 0x0e 
 
 
 
 14 
 
 
 
 KERNEL_RASTERIZER 
 
 
 
 0x4d 
 
 
 
 77 
 
 
 
 RINGBUFFER_READER 
 
 
 
 
 0x0f 
 
 
 
 15 
 
 
 
 ARG_MIN_MAX 
 
 
 
 0x4e 
 
 
 
 78 
 
 
 
 CONDITION 
 
 
 
 
 0x10 
 
 
 
 16 
 
 
 
 GLOBAL_ARG_MIN_MAX 
 
 
 
 0x4f 
 
 
 
 79 
 
 
 
 PHI 
 
 
 
 
 0x11 
 
 
 
 17 
 
 
 
 MATRIX_MULT 
 
 
 
 0x50 
 
 
 
 80 
 
 
 
 BASICBLOCK_IN 
 
 
 
 
 0x12 
 
 
 
 18 
 
 
 
 BROADCAST 
 
 
 
 0x51 
 
 
 
 81 
 
 
 
 BASICBLOCK_OUT 
 
 
 
 
 0x13 
 
 
 
 19 
 
 
 
 FLATTEN_COMPOSITE 
 
 
 
 0x52 
 
 
 
 82 
 
 
 
 BATCHNORM 
 
 
 
 
 0x14 
 
 
 
 20 
 
 
 
 UNFLATTEN_COMPOSITE 
 
 
 
 0x53 
 
 
 
 83 
 
 
 
 WAIT_FOR_EVENT 
 
 
 
 
 0x15 
 
 
 
 21 
 
 
 
 FPS_WITH_RADIUS_COMPOSITE 
 
 
 
 0x54 
 
 
 
 84 
 
 
 
 SIGNAL_EVENT 
 
 
 
 
 0x16 
 
 
 
 22 
 
 
 
 PIXEL_SHUFFLE_COMPOSITE 
 
 
 
 0x55 
 
 
 
 85 
 
 
 
 ALL_SLICE 
 
 
 
 
 0x17 
 
 
 
 23 
 
 
 
 PIXEL_UNSHUFFLE_COMPOSITE 
 
 
 
 0x56 
 
 
 
 86 
 
 
 
 ALL_GATHER 
 
 
 
 
 0x18 
 
 
 
 24 
 
 
 
 CONV_COMPOSITE 
 
 
 
 0x57 
 
 
 
 87 
 
 
 
 SCALED_DOT_PRODUCT_ATTENTION 
 
 
 
 
 0x19 
 
 
 
 25 
 
 
 
 MATDECOMP_MATMULT_COMPOSITE 
 
 
 
 0x58 
 
 
 
 88 
 
 
 
 ALL_REDUCE 
 
 
 
 
 0x1a 
 
 
 
 26 
 
 
 
 CHANNEL_TO_SPACE_LARGE_FACTOR_COMPOSITE 
 
 
 
 0x59 
 
 
 
 89 
 
 
 
 PEFUSED_ELEMENTWISE 
 
 
 
 
 0x1b 
 
 
 
 27 
 
 
 
 LIVE_IN 
 
 
 
 0x5a 
 
 
 
 90 
 
 
 
 PEFUSED_SECUREFLUSH 
 
 
 
 
 0x1c 
 
 
 
 28 
 
 
 
 LIVEIN_PARAM 
 
 
 
 0x5b 
 
 
 
 91 
 
 
 
 PEFUSED_POOL 
 
 
 
 
 0x1d 
 
 
 
 29 
 
 
 
 CONST_IN 
 
 
 
 0x5c 
 
 
 
 92 
 
 
 
 PEFUSED_GOC 
 
 
 
 
 0x1e 
 
 
 
 30 
 
 
 
 LIVE_STATE 
 
 
 
 0x5d 
 
 
 
 93 
 
 
 
 NEFUSED_CONV 
 
 
 
 
 0x1f 
 
 
 
 31 
 
 
 
 LIVE_OUT 
 
 
 
 0x5e 
 
 
 
 94 
 
 
 
 NEFUSED_KERNEL_RASTERIZER 
 
 
 
 
 0x20 
 
 
 
 32 
 
 
 
 REDUCTION 
 
 
 
 0x5f 
 
 
 
 95 
 
 
 
 NEFUSED_CROSS_CORRELATION 
 
 
 
 
 0x21 
 
 
 
 33 
 
 
 
 ALIAS 
 
 
 
 0x60 
 
 
 
 96 
 
 
 
 NEFUSED_MATMUL 
 
 
 
 
 0x22 
 
 
 
 34 
 
 
 
 REINTERPRET_INNERMOST_DIMENSION 
 
 
 
 0x61 
 
 
 
 97 
 
 
 
 NEFUSED_POOL 
 
 
 
 
 0x23 
 
 
 
 35 
 
 
 
 REINTERPRET_CAST 
 
 
 
 0x62 
 
 
 
 98 
 
 
 
 NEFUSED_EW 
 
 
 
 
 0x24 
 
 
 
 36 
 
 
 
 RESHAPE 
 
 
 
 0x63 
 
 
 
 99 
 
 
 
 NEFUSED_DUAL_SOURCE_EW 
 
 
 
 
 0x25 
 
 
 
 37 
 
 
 
 VIEW 
 
 
 
 0x64 
 
 
 
 100 
 
 
 
 NEFUSED_BYPASS 
 
 
 
 
 0x26 
 
 
 
 38 
 
 
 
 TRANSPOSE 
 
 
 
 0x65 
 
 
 
 101 
 
 
 
 NEFUSED_RCAS 
 
 
 
 
 0x27 
 
 
 
 39 
 
 
 
 SPACE_TO_BATCH 
 
 
 
 0x66 
 
 
 
 102 
 
 
 
 TRANSPOSE_ENGINE_OP 
 
 
 
 
 0x28 
 
 
 
 40 
 
 
 
 BATCH_TO_SPACE 
 
 
 
 0x67 
 
 
 
 103 
 
 
 
 TE_RESAMPLE 
 
 
 
 
 0x29 
 
 
 
 41 
 
 
 
 SPACE_TO_CHANNEL 
 
 
 
 0x68 
 
 
 
 104 
 
 
 
 TE_AFFINE_TRANSFORM 
 
 
 
 
 0x2a 
 
 
 
 42 
 
 
 
 CHANNEL_TO_SPACE 
 
 
 
 0x69 
 
 
 
 105 
 
 
 
 TE_PAD 
 
 
 
 
 0x2b 
 
 
 
 43 
 
 
 
 SOFTMAX 
 
 
 
 0x6a 
 
 
 
 106 
 
 
 
 TE_CROP_RESIZE 
 
 
 
 
 0x2c 
 
 
 
 44 
 
 
 
 INSTANCE_NORM 
 
 
 
 0x6b 
 
 
 
 107 
 
 
 
 TE_SLICE 
 
 
 
 
 0x2d 
 
 
 
 45 
 
 
 
 L2_NORM 
 
 
 
 0x6c 
 
 
 
 108 
 
 
 
 TE_GATHER 
 
 
 
 
 0x2e 
 
 
 
 46 
 
 
 
 MINMAX_NORM 
 
 
 
 0x6d 
 
 
 
 109 
 
 
 
 TE_RESIZE 
 
 
 
 
 0x2f 
 
 
 
 47 
 
 
 
 LAYER_NORM 
 
 
 
 0x6e 
 
 
 
 110 
 
 
 
 TM_WAIT_FOR_EVENT 
 
 
 
 
 0x30 
 
 
 
 48 
 
 
 
 LRN 
 
 
 
 0x6f 
 
 
 
 111 
 
 
 
 TM_SIGNAL_EVENT 
 
 
 
 
 0x31 
 
 
 
 49 
 
 
 
 COST_VOLUME 
 
 
 
 0x70 
 
 
 
 112 
 
 
 
 TM_BRANCH 
 
 
 
 
 0x32 
 
 
 
 50 
 
 
 
 PIXEL_SHUFFLE 
 
 
 
 0x71 
 
 
 
 113 
 
 
 
 TM_FETCH 
 
 
 
 
 0x33 
 
 
 
 51 
 
 
 
 PIXEL_UNSHUFFLE 
 
 
 
 0x72 
 
 
 
 114 
 
 
 
 TM_STORE 
 
 
 
 
 0x34 
 
 
 
 52 
 
 
 
 MATRIX_DECOMPOSITION 
 
 
 
 0x73 
 
 
 
 115 
 
 
 
 TM_OPERATE 
 
 
 
 
 0x35 
 
 
 
 53 
 
 
 
 FPS 
 
 
 
 0x74 
 
 
 
 116 
 
 
 
 TM_USER_SLOT_LOAD 
 
 
 
 
 0x36 
 
 
 
 54 
 
 
 
 RS 
 
 
 
 0x75 
 
 
 
 117 
 
 
 
 DMA_CONVERT 
 
 
 
 
 0x37 
 
 
 
 55 
 
 
 
 RESAMPLE 
 
 
 
 0x76 
 
 
 
 118 
 
 
 
 QUANT 
 
 
 
 
 0x38 
 
 
 
 56 
 
 
 
 GATHER 
 
 
 
 0x77 
 
 
 
 119 
 
 
 
 DEQUANT 
 
 
 
 
 0x39 
 
 
 
 57 
 
 
 
 TILE 
 
 
 
 0x78 
 
 
 
 120 
 
 
 
 SNE_COND 
 
 
 
 
 0x3a 
 
 
 
 58 
 
 
 
 SLICE 
 
 
 
 0x79 
 
 
 
 121 
 
 
 
 SNE_GOC 
 
 
 
 
 0x3b 
 
 
 
 59 
 
 
 
 PAD 
 
 
 
 0x7a 
 
 
 
 122 
 
 
 
 CCDMA_CONST 
 
 
 
 
 0x3c 
 
 
 
 60 
 
 
 
 RESIZE 
 
 
 
 0x7b 
 
 
 
 123 
 
 
 
 CCDMA_MEMORY 
 
 
 
 
 0x3d 
 
 
 
 61 
 
 
 
 RESIZEAS 
 
 
 
 0x7c 
 
 
 
 124 
 
 
 
 SPILL_FILL_DUMMY 
 
 
 
 
 0x3e 
 
 
 
 62 
 
 
 
 CROP_RESIZE 
 
 
 
 0x7d 
 
 
 
 125 
 
 
 
 INVALID 
 
 
 
 
 
 The opcode 0x3f is spelled AFFINE_TRANFORM in the
binary, a vendor source typo preserved on the wire. 
 
 
 
 C.2 Operation-attribute schema and IOKit external-method
struct
layouts 

 
 The attribute schema is string-keyed: the token is the wire encoding the
compiler matches on, and most integer constants are not recoverable
statically. The converter recognizes 171 literal attribute keys, of
which roughly 140 are op-facing. Table   C.8 gives
representative keys with their value types, meanings, and wire
encodings. 
 
 
 Table C.8: Representative operation-attribute keys with their value types,
meanings, and wire
encodings. 
 
 
 
 
 
 key 
 
 
 
 type 
 
 
 
 meaning 
 
 
 
 value encoding 
 
 
 
 
 
 
 activation 
 
 
 
 enum 
 
 
 
 neuron mode 
 
 
 
 token into the 22-field PWL
descriptor 
 
 
 
 
 strides 
 
 
 
 int[] 
 
 
 
 per-axis stride 
 
 
 
 NDCHW
int array; deconv restricted to {1,2} 
 
 
 
 
 groups 
 
 
 
 int 
 
 
 
 group count 
 
 
 
 channel-wise requires
 groups == out.C 
 
 
 
 
 padding_mode 
 
 
 
 enum 
 
 
 
 fill rule 
 
 
 
 constant / reflect / replicate /
 symmetric 
 
 
 
 
 weights_layout 
 
 
 
 enum 
 
 
 
 weight axis order 
 
 
 
 NCHW /
 NHWC / OIHW / HWIO ; weight buffer is
 MACI 
 
 
 
 
 compressed 
 
 
 
 bool/enum 
 
 
 
 weight compression 
 
 
 
 format set by the MIL-op-count contract 
 
 
 
 
 interleave 
 
 
 
 int 
 
 
 
 channel-tiling quantum 
 
 
 
 one of
{1,2,3,4,8} 
 
 
 
 
 epsilon 
 
 
 
 float 
 
 
 
 norm stability 
 
 
 
 scalar 
 
 
 
 
 
 The host-to-kernel IOKit dispatch key is the (selector, struct-size)
tuple, not the selector alone. Table   C.9 gives the
control-client selectors with their method names and decoded input and
output struct sizes. 
 
 
 Table C.9: The IOKit control-client selectors with their method names and
decoded input and output struct
sizes. 
 
 
 
 sel 
 method 
 in-struct 
 out/scalar 
 
 
 
 0 
 ANE_DeviceOpen 
 104 
 104 
 
 2 
 ANE_ProgramSendRequest 
 2376 + 1 scalar 
 40 async 
 
 3 
 ANE_ProgramCreate 
 32 
 0 
 
 4 
 ANE_ProgramPrepare 
 56 
 56 
 
 6 
 ANE_ProgramDestroy 
 16 
 0 
 
 7 
 ANE_GetStatus 
 0 
 32 
 
 8 
 ANE_ProgramCreateInstance 
 32 
 0 
 
 10 
 ANE_GetVersion 
 0 
 1 scalar 
 
 21 
 ANE_ProgramInputsReady 
 3104 
 0 
 
 22 
 ANE_MemoryMapRequest 
 2080 + 1 scalar 
 1 scalar 
 
 
 
 
 The ANEDeviceOpen shared in/out buffer (104 bytes, selector 0)
decodes by byte offset as table   C.10 . 
 
 
 Table C.10: The field layout of the ANEDeviceOpen shared input and output
buffer by byte offset. 
 
 
 
 offset 
 field 
 
 
 
 +0x00 
 usage type (1 standard, 2 unsupported) plus session
token 
 
 +0x08 
 callback function pointer 
 
 +0x10 
 receiver context pointer 
 
 +0x18 
 timeout 0x2710 (10000) 
 
 +0x48 
 version pair 32, 256 
 
 +0x50 
 NumANEs 0, 1 
 
 
 
 
 The full 171-key attribute corpus, the decoded enum-value tables, and
the per-selector field layouts for the HW direct-path client are in the
research corpus. 
 
 
 
 C.3 Numeric error, status, and return
codes 

 
 The ANE stack has no flat numeric status enum. The fixed numeric values
that exist are the IOKit return constants and the firmware magic and
sentinel words, the first of which table   C.11 gives with
their meanings on the dispatch path. 
 
 
 Table C.11: The IOKit return constants and their meanings on the engine
dispatch path. 
 
 
 
 
 
 macro 
 
 
 
 hex 
 
 
 
 ANE path meaning 
 
 
 
 
 
 
 kIOReturnSuccess 
 
 
 
 0x00000000 
 
 
 
 success 
 
 
 
 
 kIOReturnError 
 
 
 
 0xe0000001 
 
 
 
 general
failure 
 
 
 
 
 kIOReturnBusy 
 
 
 
 0xe0000007 
 
 
 
 gate or command busy 
 
 
 
 
 kIOReturnNoMemory 
 
 
 
 0xe00002bd 
 
 
 
 allocation failure 
 
 
 
 
 kIOReturnNoResources 
 
 
 
 0xe00002be 
 
 
 
 out of resources,
queue or slot exhaustion 
 
 
 
 
 kIOReturnNotPrivileged 
 
 
 
 0xe00002c1 
 
 
 
 privilege check failed 
 
 
 
 
 kIOReturnBadArgument 
 
 
 
 0xe00002c2 
 
 
 
 typed-args
validation failure 
 
 
 
 
 kIOReturnUnsupported 
 
 
 
 0xe00002c7 
 
 
 
 disabled or stub path; also what a gated feature returns when its
entitlement is absent 
 
 
 
 
 kIOReturnNotReady 
 
 
 
 0xe00002d0 
 
 
 
 device or channel not
ready 
 
 
 
 
 kIOReturnAborted 
 
 
 
 0xe00002eb 
 
 
 
 request aborted 
 
 
 
 
 kIOReturnNotFound 
 
 
 
 0xe00002f0 
 
 
 
 program or process
handle not found 
 
 
 
 
 kIOReturnTimeout 
 
 
 
 0xe0000404 
 
 
 
 firmware op timed out 
 
 
 
 
 
 At every layer the error surface is name-based or message-based. The
client-visible surface above IOKit is an error factory that wraps the
lower-layer code into a structured error across four domains, named
 errorDomainCompiler , errorDomainEspresso ,
 errorDomainGeneric , and errorDomainVirtIO . Its factory
methods are the taxonomy: a generic wrapper, a missing-code-signing
form, program-load and new-instance-load forms that hold the lower-layer
code, surface map and unmap forms, and a virtualization-kernel form. The
single most look-up-worthy client-visible value is 0xe00002c7 
( kIOReturnUnsupported ), returned on a disabled or unsupported
path and when a gated feature’s entitlement is absent. 
 
 
 Table   C.12 gives the fixed firmware magic words and
sentinel constants with their meanings. 
 
 
 Table C.12: The fixed firmware magic words and sentinel constants with
their meanings. 
 
 
 
 
 
 constant 
 
 
 
 hex 
 
 
 
 meaning 
 
 
 
 
 
 
 package magic 
 
 
 
 0x414E4548 ( ANEH ) 
 
 
 
 loader package
header 
 
 
 
 
 program magic 
 
 
 
 0x414E4550 ( ANEP ) 
 
 
 
 loader program header 
 
 
 
 
 section magic 
 
 
 
 0x414E4553 ( ANES ) 
 
 
 
 loader section
header 
 
 
 
 
 AFPP control magic 
 
 
 
 0x55AA55AA 
 
 
 
 AFPP control
struct 
 
 
 
 
 checksum-valid sentinel 
 
 
 
 0xFFFFFFFF 
 
 
 
 command checksum
initialized and valid 
 
 
 
 
 invalid id 
 
 
 
 0xFFFFFFFF 
 
 
 
 ECSneCmdId_Invalid , unbound program or process 
 
 
 
 
 padding 
 
 
 
 0x00000000 
 
 
 
 command padding must be zero 
 
 
 
 
 power-status byte 
 
 
 
 0xFF / 0x00 
 
 
 
 fully on / fully off 
 
 
 
 
 
 This section shows the three loader magic words as 32-bit integers; on
disk the bytes are little-endian, so a raw byte scan finds
 HENA , PENA , and SENA (the characters of
 ANEH , ANEP , ANES reversed). The
firmware-to-host notification names, inline status=0x%x print
sites, AArch64 and L2C fault-register dump fields, and compiler
diagnostic categories are in the research corpus. 
 
 
 
 C.4 The tunable register-init
table 

 
 The per-chip register init is a sequence of 12-byte
 (offset, mask, value) records, each applied as a masked
read-modify-write,
 reg = (reg & ~mask) | value ,
where reg is the block MMIO base plus the offset. The M1 (ASC
AscChinook) firmware has 1994 records across 10 named MMIO blocks, each
block reached through a 32-byte descriptor of name, MMIO base, record
pointer, and count, the blocks and their counts given in
 table   C.13 . 
 
 
 Table C.13: The named MMIO register-init blocks with their bases and record
counts. 
 
 
 
 block name 
 MMIO base 
 records 
 
 
 
 ASC_CHINOOK 
 0x2_6b00_0000 
 24 
 
 ASCWRAP 
 0x2_6b40_0000 
 2 
 
 sneCtrl 
 0x2_6b84_0000 
 15 
 
 ANE 
 0x2_6bc0_0000 
 47 
 
 aneDpePpt 
 0x2_6b8e_c000 
 304 
 
 aneDpePptAccp0 
 0x2_6b8e_d000 
 528 
 
 aneDpePptAccp1 
 0x2_6b8e_e000 
 528 
 
 aneDpePptAccp2 
 0x2_6b8e_f000 
 528 
 
 aneDpeSys 
 0x2_6b8f_0000 
 9 
 
 aneDpePpt_soc_dpe_lee 
 0x2_6b8f_4000 
 9 
 
 
 
 
 Table   C.14 gives representative records, one or more
per block, with their address, mask, value, and meaning. 
 
 
 Table C.14: Representative register-init records with their address, mask,
value, and meaning. 
 
 
 
 
 
 regAddr 
 
 
 
 mask 
 
 
 
 value 
 
 
 
 meaning 
 
 
 
 
 
 
 0x2_6b14_0020 
 
 
 
 0xf80000 
 
 
 
 0x780000 
 
 
 
 ASC
clock or PLL divider field set to 15 
 
 
 
 
 0x2_6b40_080c 
 
 
 
 0x6000_0001 
 
 
 
 0x6000_0001 
 
 
 
 fabric clock and QoS enable 
 
 
 
 
 0x2_6b84_0028 .. 0044 
 
 
 
 0x8fff_c000 
 
 
 
 0x8fff_c000 
 
 
 
 8 identical SNE QoS and credit words, one per
set 
 
 
 
 
 0x2_6bc0_d014 .. fec4 
 
 
 
 0x1 
 
 
 
 0x1 
 
 
 
 32 per-tile MAC clock and power enables 
 
 
 
 
 0x2_6bc1_400c 
 
 
 
 0xffff_ff00 
 
 
 
 0x4010_1000 
 
 
 
 DMA descriptor base and config word 
 
 
 
 
 0x2_6b8e_c000 
 
 
 
 0xffff 
 
 
 
 0x267e 
 
 
 
 peak-power-tracking base budget word 
 
 
 
 
 0x2_6b8e_c42c 
 
 
 
 0x3fff 
 
 
 
 0x0 
 
 
 
 DPE
trailing-control reg, armed live to 0x3fff 
 
 
 
 
 0x2_6b8e_d000 
 
 
 
 0xffff_ffff 
 
 
 
 0x0077_3594 
 
 
 
 per-counter energy scale coefficient
(7811476) 
 
 
 
 
 0x2_6b8f_0014 
 
 
 
 0xffff_ffff 
 
 
 
 0x0000_23e1 
 
 
 
 DPE config and period word 
 
 
 
 
 0x2_6b8f_0038 
 
 
 
 0xffff_ffff 
 
 
 
 0x0003_2dcc 
 
 
 
 DPE accumulation window and divisor (207820) 
 
 
 
 
 0x2_6b8f_4000 
 
 
 
 0x1e 
 
 
 
 0xc 
 
 
 
 SoC-level LEE
control field 
 
 
 
 
 
 The 32 mask=1 value=1 records at a regular stride are direct
evidence of the 32-tile MAC array geometry, each tile individually clock
and power gateable. The DPE system block has seven ascending sampling
thresholds (25, 50, 70, 85, 95, 105, 115), and the SoC
leakage-estimation block has eight (10, 22, 39, 64, 89, 121, 164, 189):
the firmware-side breakpoints of the power model. All 1994 decoded
records are in the research corpus. 
 
 
 
 C.5 The CSNE_CMD_* numeric command
table 

 
 The host-to-firmware command set is 93 entries, numbered 0x00 
through 0x5c , indexed by eCSneCmdId into the firmware
command-name string table, whose index is the numeric command
identifier. 0xFFFFFFFF is the no-command sentinel.
 Table   C.15 gives the full set; its dir column
is H->FW for a host request and
 FW->H for a firmware notification, and the
subsystem codes are lifecycle, power, secure, program, execution, cache,
ipc, buffer, property, and stats. 
 
 
 Table C.15: The complete 93-entry host-to-firmware command table with name,
direction, subsystem, and
purpose. 
 
 
 
 
 
 id 
 
 
 
 name 
 
 
 
 dir 
 
 
 
 subsystem 
 
 
 
 purpose 
 
 
 
 
 
 
 0x00 
 
 
 
 STOP 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 stop the controller 
 
 
 
 
 0x01 
 
 
 
 RESET 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 reset controller state 
 
 
 
 
 0x02 
 
 
 
 CONFIG_GET 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 read config blob 
 
 
 
 
 0x03 
 
 
 
 PRINT_ENABLE 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 enable firmware print 
 
 
 
 
 0x04 
 
 
 
 REG_FILE_LOAD 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 load a register file 
 
 
 
 
 0x05 
 
 
 
 BUILDINFO 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 return firmware build
string 
 
 
 
 
 0x06 
 
 
 
 TIMEPROFILE_START 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 begin time-profiling 
 
 
 
 
 0x07 
 
 
 
 TIMEPROFILE_STOP 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 stop time-profiling 
 
 
 
 
 0x08 
 
 
 
 TIMEPROFILE_SHOW 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 dump profile 
 
 
 
 
 0x09 
 
 
 
 FW_RUN_MODE 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 select firmware run mode 
 
 
 
 
 0x0a 
 
 
 
 POWER_DOWN 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 full power-down 
 
 
 
 
 0x0b 
 
 
 
 SET_SNE_PMU_BASE 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 set PMU MMIO base 
 
 
 
 
 0x0c 
 
 
 
 SET_SNE_RPC_CHECK_CMD 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 RPC sanity-check command 
 
 
 
 
 0x0d 
 
 
 
 RPC_ENABLE 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 enable the back-channel RPC
channel 
 
 
 
 
 0x0e 
 
 
 
 PLATFORM_INFO 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 platform descriptor 
 
 
 
 
 0x0f 
 
 
 
 BOOT 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 bring firmware to booted
state 
 
 
 
 
 0x10 
 
 
 
 PING 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 liveness probe 
 
 
 
 
 0x11 
 
 
 
 CONFIG_GET_EXT 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 extended config read 
 
 
 
 
 0x12 
 
 
 
 POWER_DEVICE_ON 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 power the device on 
 
 
 
 
 0x13 
 
 
 
 POWER_DEVICE_OFF 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 power device off 
 
 
 
 
 0x14 
 
 
 
 IPC_ENDPOINT_SET 
 
 
 
 H->FW 
 
 
 
 ipc 
 
 
 
 bind an IPC endpoint 
 
 
 
 
 0x15 
 
 
 
 IPC_ENDPOINT_UNSET 
 
 
 
 H->FW 
 
 
 
 ipc 
 
 
 
 unbind endpoint 
 
 
 
 
 0x16 
 
 
 
 CH_INFO_GET 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 channel info query 
 
 
 
 
 0x17 
 
 
 
 CH_BUFFER_RECYCLE_MODE_SET 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 set buffer-recycle mode 
 
 
 
 
 0x18 
 
 
 
 CH_BUFFER_RECYCLE_START 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 start recycling 
 
 
 
 
 0x19 
 
 
 
 CH_BUFFER_RECYCLE_STOP 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 stop recycling 
 
 
 
 
 0x1a 
 
 
 
 CH_BUFFER_RETURN 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 return one pooled buffer 
 
 
 
 
 0x1b 
 
 
 
 CH_BUFFER_POOL_CONFIG_GET 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 read buffer-pool config 
 
 
 
 
 0x1c 
 
 
 
 CH_BUFFER_POOL_CONFIG_SET 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 configure buffer-pool 
 
 
 
 
 0x1d 
 
 
 
 CH_DATA_FILE_LOAD 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 stream a data file over
channel 
 
 
 
 
 0x1e 
 
 
 
 CH_PROPERTY_WRITE 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 write a register or property 
 
 
 
 
 0x1f 
 
 
 
 CH_PROPERTY_READ 
 
 
 
 H->FW 
 
 
 
 property 
 
 
 
 read a register or property 
 
 
 
 
 0x20 
 
 
 
 TRACE_ENABLE 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 enable tracing 
 
 
 
 
 0x21 
 
 
 
 RESOURCE_INFO_GET 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 query engine resources 
 
 
 
 
 0x22 
 
 
 
 STATS_BUFFER_SIZE_GET 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 compute required stats-buffer
size 
 
 
 
 
 0x23 
 
 
 
 SUSPEND 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 suspend engine 
 
 
 
 
 0x24 
 
 
 
 DSID_SET 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 set data-set identifiers for prefetch 
 
 
 
 
 0x25 
 
 
 
 MCACHE_SIZE_GET 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 query memory-cache size 
 
 
 
 
 0x26 
 
 
 
 SECURE_MODE_START 
 
 
 
 H->FW 
 
 
 
 secure 
 
 
 
 enter secure mode 
 
 
 
 
 0x27 
 
 
 
 SECURE_MODE_STOP 
 
 
 
 H->FW 
 
 
 
 secure 
 
 
 
 leave secure mode 
 
 
 
 
 0x28 
 
 
 
 SET_SNE_PMU_BASE2 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 version 2 PMU base set 
 
 
 
 
 0x29 
 
 
 
 IPC_ENDPOINT_SET2 
 
 
 
 H->FW 
 
 
 
 ipc 
 
 
 
 version 2 endpoint bind 
 
 
 
 
 0x2a 
 
 
 
 IPC_ENDPOINT_UNSET2 
 
 
 
 H->FW 
 
 
 
 ipc 
 
 
 
 version 2 unbind 
 
 
 
 
 0x2b 
 
 
 
 CH_DATA_FILE_LOAD2 
 
 
 
 H->FW 
 
 
 
 buffer 
 
 
 
 version 2 data-file load 
 
 
 
 
 0x2c 
 
 
 
 SET_DYNAMIC_POWERGATE 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 configure dynamic clock and power
gating 
 
 
 
 
 0x2d 
 
 
 
 ANE_DEFAULT_SETTING_SET 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 bulk default-settings push 
 
 
 
 
 0x2e 
 
 
 
 INIT_SHARED_EVENT_INFO 
 
 
 
 H->FW 
 
 
 
 ipc 
 
 
 
 initialize shared-event table 
 
 
 
 
 0x2f 
 
 
 
 EXCLAVE_MODE_START 
 
 
 
 H->FW 
 
 
 
 secure 
 
 
 
 enter exclave mode (stubbed on
H13) 
 
 
 
 
 0x30 
 
 
 
 EXCLAVE_MODE_STOP 
 
 
 
 H->FW 
 
 
 
 secure 
 
 
 
 leave exclave mode 
 
 
 
 
 0x31 
 
 
 
 QUIESCE_STATE 
 
 
 
 H->FW 
 
 
 
 lifecycle 
 
 
 
 drain in-flight work 
 
 
 
 
 0x32 
 
 
 
 CPU_LOAD_GET 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 sample CPU load 
 
 
 
 
 0x33 
 
 
 
 SECURE_MODE_RESUME_TRANSITION 
 
 
 
 H->FW 
 
 
 
 secure 
 
 
 
 resume a paused secure transition 
 
 
 
 
 0x34 
 
 
 
 CH_ERROR_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 error notification 
 
 
 
 
 0x35 
 
 
 
 CH_POWER_CONTROL 
 
 
 
 H->FW 
 
 
 
 power 
 
 
 
 channel-level power control 
 
 
 
 
 0x36 
 
 
 
 CH_SIGNPOST_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 32-bit signpost notification 
 
 
 
 
 0x37 
 
 
 
 CH_SIGNPOST_NOTIFICATION_GROUP 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 grouped 32-bit signpost 
 
 
 
 
 0x38 
 
 
 
 CH_RESET_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 reset notification 
 
 
 
 
 0x39 
 
 
 
 CH_SIGNPOST64_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 64-bit signpost 
 
 
 
 
 0x3a 
 
 
 
 CH_SIGNPOST64_NOTIFICATION_GROUP 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 grouped 64-bit signpost 
 
 
 
 
 0x3b 
 
 
 
 CPU_LOAD_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 CPU-load notification 
 
 
 
 
 0x3c 
 
 
 
 TM_SYNC_ERR_NOTIFICATION 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 tile-manager sync error 
 
 
 
 
 0x3d 
 
 
 
 LOAD_PROGRAM 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 load a compiled program into a
slot 
 
 
 
 
 0x3e 
 
 
 
 UNLOAD_PROGRAM 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 unload a program 
 
 
 
 
 0x3f 
 
 
 
 CREATE_PROCESS 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 instantiate a process for a
program 
 
 
 
 
 0x40 
 
 
 
 TERMINATE_PROCESS 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 tear down a process 
 
 
 
 
 0x41 
 
 
 
 PROCEDURE_CALL 
 
 
 
 H->FW 
 
 
 
 execution 
 
 
 
 baseline network invocation 
 
 
 
 
 0x42 
 
 
 
 LOAD_AFPP 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 load AFPP prefetch program 
 
 
 
 
 0x43 
 
 
 
 UNLOAD_AFPP 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 unload AFPP 
 
 
 
 
 0x44 
 
 
 
 PROGRAM_INTERFACE_VERSION_CHECK 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 negotiate program-interface
version 
 
 
 
 
 0x45 
 
 
 
 PROCEDURE_CALL_CACHE_REQUEST 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 install a resident cache
request 
 
 
 
 
 0x46 
 
 
 
 PROCEDURE_CALL_TRIGGER_CACHE_REQUEST 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 fire an installed cache request 
 
 
 
 
 0x47 
 
 
 
 PROCEDURE_CALL_RECYCLE_OUTPUT_BUFFER 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 return a consumed output buffer 
 
 
 
 
 0x48 
 
 
 
 PROCEDURE_CALL_INVALIDATE_CACHE_REQUEST 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 destroy a cache request 
 
 
 
 
 0x49 
 
 
 
 PROCEDURE_CALL_WITH_CUSTOM_BARS 
 
 
 
 H->FW 
 
 
 
 execution 
 
 
 
 proc-call with custom barrier
array 
 
 
 
 
 0x4a 
 
 
 
 PREMAP_BUFFER 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 pre-map an inference-property buffer 
 
 
 
 
 0x4b 
 
 
 
 PROCEDURE_CALL_CACHE_REQUEST_WITH_CUSTOM_BARS 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 cache request with custom bars 
 
 
 
 
 0x4c 
 
 
 
 PROCEDURE_CALL_CACHE_REQUEST_WITH_SHARED_EVENTS 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 cache request with shared
events 
 
 
 
 
 0x4d 
 
 
 
 FORCE_DISABLE_CACHE_REQUESTS 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 global cache-request disable 
 
 
 
 
 0x4e 
 
 
 
 PROCEDURE_CALL_WITH_SIGNAL_EVENTS 
 
 
 
 H->FW 
 
 
 
 execution 
 
 
 
 proc-call with wait and signal
events 
 
 
 
 
 0x4f 
 
 
 
 SET_ACTIVE_CACHE_REQUEST_IN_GROUP 
 
 
 
 H->FW 
 
 
 
 cache 
 
 
 
 select active member of a
cache-request group 
 
 
 
 
 0x50 
 
 
 
 PROGRAM_EVENT 
 
 
 
 FW->H 
 
 
 
 program 
 
 
 
 per-program event notification 
 
 
 
 
 0x51 
 
 
 
 USER_EVENT 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 user event marker 
 
 
 
 
 0x52 
 
 
 
 DBG_EVENT 
 
 
 
 FW->H 
 
 
 
 stats 
 
 
 
 debug event 
 
 
 
 
 0x53 
 
 
 
 DATA_CHAINING_EVENT 
 
 
 
 FW->H 
 
 
 
 cache 
 
 
 
 data-chaining stage completion 
 
 
 
 
 0x54 
 
 
 
 PREFETCH_DSID_EVENT 
 
 
 
 FW->H 
 
 
 
 cache 
 
 
 
 prefetch completion 
 
 
 
 
 0x55 
 
 
 
 SECURE_MODE_EVENT 
 
 
 
 FW->H 
 
 
 
 secure 
 
 
 
 secure-mode state-change event 
 
 
 
 
 0x56 
 
 
 
 REQUEST_PROGRAM_ID 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 allocate a program-id slot 
 
 
 
 
 0x57 
 
 
 
 RETURN_PROGRAM_ID 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 free a program-id slot 
 
 
 
 
 0x58 
 
 
 
 REQUEST_PROCESS_ID 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 allocate a process-id 
 
 
 
 
 0x59 
 
 
 
 RETURN_PROCESS_ID 
 
 
 
 H->FW 
 
 
 
 program 
 
 
 
 free a process-id 
 
 
 
 
 0x5a 
 
 
 
 INFERENCE_CALL 
 
 
 
 H->FW 
 
 
 
 execution 
 
 
 
 high-level inference submission 
 
 
 
 
 0x5b 
 
 
 
 BACK_CHANNEL_RPC 
 
 
 
 FW<->H 
 
 
 
 property 
 
 
 
 firmware-initiated
back-channel RPC 
 
 
 
 
 0x5c 
 
 
 
 DEBUG_COMMAND_DATA_CHECK 
 
 
 
 H->FW 
 
 
 
 stats 
 
 
 
 validate command-data integrity 
 
 
 
 
 
 Two strings the prior corpus counted have no numeric identifier:
 CSNE_CMD_START is a standalone lifecycle log alias, and
 CSNE_CMD_IPC_ENDPOINT_TYPE_DATA_CHAINING is an
endpoint-type enum value rather than a command. The per-call numeric
limits the command bodies enforce on the M1 are fixed. The dispatch caps
are at most 16 signal events per call, at most 32 custom barriers on the
wire (128 in the program container), at most 128 custom execute-order
entries, at most 16 trigger input buffers, and fewer than 2 active
shared events. Priority levels run 0 through 7, split into a privileged
band of 0 and 1 and a normal band of 2 through 7. The single dispatch
path takes exactly one output buffer set, one task-descriptor partition,
and one engine request per list. 
 
 
 Table   C.16 gives the fixed-header layout
( sCSneControllerCmdHdr ) that prefixes every ring message, with
each field’s offset, width, and meaning. 
 
 
 Table C.16: The fixed command-header fields with their offsets, widths, and
meanings. 
 
 
 
 
 
 field 
 
 
 
 offset 
 
 
 
 width 
 
 
 
 meaning 
 
 
 
 
 
 
 id 
 
 
 
 0x00 
 
 
 
 u32 
 
 
 
 the eCSneCmdId 
selector 
 
 
 
 
 size 
 
 
 
 0x04 
 
 
 
 u32 
 
 
 
 byte
length of the command body 
 
 
 
 
 priority 
 
 
 
 0x08 
 
 
 
 u32 
 
 
 
 scheduling band, 0..7
(0..1 realtime, 2..7 normal) 
 
 
 
 
 programId 
 
 
 
 0x0c 
 
 
 
 i32 
 
 
 
 loaded-program slot, -1 invalid 
 
 
 
 
 processId 
 
 
 
 0x10 
 
 
 
 i32 
 
 
 
 per-program process
instance, -1 none 
 
 
 
 
 procedureId 
 
 
 
 0x14 
 
 
 
 u32 
 
 
 
 index into the program’s procedure table 
 
 
 
 
 
 The full 93-entry table with file offsets, the decoded request structs,
and the per-call numeric limits are in the research corpus. 
 
 
 
 C.6 The task-descriptor hardware register
map 

 
 A captured ane_reg record is a (regAddr, regValue) 
pair whose low address selects one of 7 aperture groups.
 Table   C.17 is the aperture map that converts a raw
address to a group, with the image base and window of each. 
 
 
 Table C.17: The register-address ranges and the aperture group, image base,
and window each maps to. 
 
 
 
 
 
 regAddr range 
 
 
 
 group 
 
 
 
 image base 
 
 
 
 window 
 
 
 
 
 
 
 < 0x4c 
 
 
 
 G1 dimensions 
 
 
 
 0xf4 
 
 
 
 19 words 
 
 
 
 
 0x4100 .. 0x4177 
 
 
 
 G3 elementwise /
planar / pad 
 
 
 
 0x264 
 
 
 
 30 words 
 
 
 
 
 0x4500 .. 0x4537 
 
 
 
 G4 L2 / texture 
 
 
 
 0x2e4 
 
 
 
 14 words 
 
 
 
 
 0x4900 .. 0x492b 
 
 
 
 G5 kernel-fmt /
op-mode 
 
 
 
 0x324 
 
 
 
 11 words 
 
 
 
 
 0x4d00 .. 0x4e13 
 
 
 
 G2 tile DMA 
 
 
 
 0x148 
 
 
 
 69
words 
 
 
 
 
 0x5100 .. 0x5153 
 
 
 
 G6 L2-result 
 
 
 
 0x358 
 
 
 
 21 words 
 
 
 
 
 0x5500 .. 0x5587 
 
 
 
 G0 kernel / common 
 
 
 
 0x24 
 
 
 
 34 words 
 
 
 
 
 
 Table   C.18 gives representative G1 dimension fields, which
also pack the format and control bits, with the bit range and width of
each. 
 
 
 Table C.18: Representative G1 dimension register fields with their bit
ranges, widths, and meanings. 
 
 
 
 regAddr 
 field 
 bits 
 width 
 meaning 
 
 
 
 0x00 
 Win 
 [14:0] 
 15 
 input tile width 
 
 0x02 
 Hin 
 [14:0] 
 15 
 input tile
height 
 
 0x0c 
 Cin 
 [16:0] 
 17 
 input channels, max 131071 
 
 0x10 
 Cout 
 [16:0] 
 17 
 output
channels 
 
 0x10 
 CommonInFmt 
 [1:0] 
 2 
 source-1 element format 
 
 0x10 
 CommonOutFmt 
 [5:4] 
 2 
 output
element format 
 
 0x28 
 numGroups 
 [12:0] 
 13 
 convolution groups 
 
 0x38 
 CommonTaskType 
 [7:4] 
 4 
 hardware task class (9 valid) 
 
 
 
 
 To invert a raw value: DMA strides are 26-bit signed at bits [31:6];
L2-result base and strides are 17-bit at bits [20:4]; a full device
address is (hi << 32) | lo 
with lo 64-byte aligned and hi 10 bits, capped at 42
bits. The complete inventory of roughly 190 register fields across the 7
groups, 11 reloc slots, and on-M1 stubbed engines (CCDMA, atomic
scatter, LDTID) is in the research corpus. 
 
 
 Each operation descriptor in the task-descriptor stream has a 32-bit
opcode word. Table   C.19 gives the words decoded from a
live M1 program for three operations. 
 
 
 Table C.19: The version-7 / H13 codegen opcode words for three operations,
with the high half-word shared and the low 16 bits selecting the
operation. 
 
 
 
 operation 
 opcode word 
 
 
 
 convolution 
 0x5042a063 
 
 reduce-mean 
 0x5000a021 
 
 matrix multiply 
 0x5000b021 
 
 
 
 
 
 C.7 The .e5 FlatBuffer
schema 

 
 The program container is a FlatBuffer whose root table holds four
fields, the schema given as listing   78 . The schema
reconstructs from the serializer method set and the wire bytes, since
the binary strips the reflection schema, and round-trips cleanly through
the FlatBuffers tool to 23 tables, 4 enums, and 1 union. The data-type
and op-type enums are recovered by name; the numeric ordinals are
inferred. 
 
 
 List of listings 78 The reconstructed program-container FlatBuffer schema: root table, type enums, tensor descriptor, section tables, and operation structure. 
 
 
 
 
 namespace E5RT.fb; 
 
 
 enum TensorDataType : int { 
 
 
 Invalid = 0 , Float16 = 1 , Float32 = 2 , Int8 = 3 , UInt8 = 4 , 
 
 
 Int16 = 5 , Int32 = 6 , Int4 = 7 , Bool = 8 , E4M3 = 9 , E5M2 = 10 
 
 
 } 
 
 
 enum OpType : int { 
 
 
 Cast = 0 , AneInference = 1 , EirInference = 2 , CpuInference = 3 , 
 
 
 BnnsCpuInference = 4 , MlcCpuInference = 5 , MpsGraphInference = 6 , 
 
 
 E5MinimalCpu = 7 , Quant = 8 , Dequant = 9 , Barrier = 10 , JitCall = 11 
 
 
 } 
 
 
 table TensorDescriptor { 
 
 
 dim:[ ulong ]; 
 
 
 stride:[ ulong ]; 
 
 
 width: ulong ; 
 
 
 height: ulong ; 
 
 
 channels: ulong ; 
 
 
 batch_number: ulong ; 
 
 
 sequence_length: ulong ; 
 
 
 stride_width: ulong ; 
 
 
 stride_height: ulong ; 
 
 
 stride_channels: ulong ; 
 
 
 stride_batch_number: ulong ; 
 
 
 stride_sequence_length: ulong ; 
 
 
 storage_type:TensorDataType; 
 
 
 component_pack: int ; 
 
 
 } 
 
 
 table BuildInfoEntry { key: string ; value: string ; } 
 
 
 table BuildInfo { entries:[BuildInfoEntry]; } // 7 key-value pairs in the sample 
 
 
 table AliasSymbol { name: string ; symbol_index: uint ; addr_offset: uint ; } 
 
 
 table IOPort { name: string ; byte_size: ulong ; aperture_va: ulong ; } 
 
 
 table Operand { descriptor:TensorDescriptor; } 
 
 
 table CastAttrs { src_dtype:TensorDataType; dst_dtype:TensorDataType; component_pack: int ; } 
 
 
 table AneInferenceAttrs { 
 
 
 procedure_name: string ; 
 
 
 anehash: string ; 
 
 
 program_symbol: string ; 
 
 
 intermediate_buffer_handle: uint ; 
 
 
 compiler_options: string ; 
 
 
 } 
 
 
 table Operation { 
 
 
 name: string ; 
 
 
 op_type:OpType; 
 
 
 inputs:[ uint ]; 
 
 
 outputs:[ uint ]; 
 
 
 arg_frame: string ; // __arg_frame section reference 
 
 
 attrs_section: string ; // __op_attrs section reference 
 
 
 } 
 
 
 table Block { name: string ; operations:[Operation]; } 
 
 
 table Function { name: string ; anehash_path: string ; blocks:[Block]; } 
 
 
 table Section { name: string ; kind: int ; } 
 
 
 table E5Program { 
 
 
 symbol_names:[ string ]; // field[0] name vector 
 
 
 build_info:BuildInfo; // field[1] 7-entry sub-table 
 
 
 sections:[Section]; // field[2] 6-entry section vector 
 
 
 format_version: int ; // field[3] inline scalar == 4 
 
 
 } 
 
 
 root_type E5Program; 
 
 
 
 The whole fused graph collapses to a single AneInference 
operation, with the surrounding Cast operations holding the
input and output dtype conversion. The validation against the round-9
 H13C.e5 sample reads the four root fields, the seven build-info
pairs ( built-for-profiling , input-file-path , the
component versions, and on-device-compilation ), and the
operation chain Cast , AneInference , Cast 
straight out of the bytes with no contradiction. The enum ordinals, the
 e4m3 and e5m2 dtypes, segment-chaining fields, and
field sets of the ten op-attribute tables other than CastAttrs 
and AneInferenceAttrs are inferred rather than byte-confirmed
in this single-segment sample. 
 
 
 
 
 Appendix D Glossary 

 
 
 SUMMARY 
 This appendix defines the acronyms, proper nouns, and symbols the guide
uses across all nine parts. Read the four core facts first, then the
term table, then the family and silicon map. 
 
 
 
 The term table   D.1 is the reference; the notes after it
record the core facts that the rest of the guide depends on. 
 
 
 D.1 Core facts 

 
 Read these four corrections before the table; several entries below
depend on them. The M5 base part is H17, specifically the h17s 
compiler target, not H16s; H16s and H17s are separate targets
distinguished only by the generation-tag byte. The multiply-accumulate
datapath uses a single wide accumulator of the fp32 class, supplied by
radix-4 fp16-rounded input tiles; the accumulator width is fixed
hardware on every device and is never a per-chip parameter, so it is not
a recursive fp16 reduction tree. On M1/H13 two weight-compression forms
stream natively, the int4 palette (int4-LUT) and the sparse form whose
mask and values have at least 50 percent zeros; int8 and
blockwise-affine weights fold into the descriptor on that generation and
only stream natively from later families. The firmware task-queue
notification identifier (NID) is 8-bit, taking values 1 through 255. 
 
 
 
 D.2 Terms 

 
 Table D.1: The acronyms, proper nouns, and symbols used across the guide
with their definitions. 
 
 
 
 
 
 Term 
 
 
 
 Definition 
 
 
 
 
 
 
 A11 through A18, M1 through M5 
 
 
 
 Apple system-on-chip marketing names,
each with an ANE of a specific H-generation, related by
 M ⁡ ( n ) = H ⁡ ( n + 12 ) M(n)=H(n+12) . 
 
 
 
 
 AFPP 
 
 
 
 The on-device firmware program container: a
three-level big-endian FourCC package, ANEH then ANEP 
then sections. 
 
 
 
 
 aned 
 
 
 
 The system ANE broker daemon at
 /usr/libexec/aned that holds the IOKit access gate, so every
unentitled client reaches the engine by sending it a request. 
 
 
 
 
 aneuserd 
 
 
 
 The per-user sibling of
 aned , the other holder of the IOKit access gate. 
 
 
 
 
 ANEC, anec.* 
 
 
 
 The compiler backend intermediate-language
dialect of 97 operations, the target of front-end lowering and the input
to task-descriptor codegen. 
 
 
 
 
 ANECCompile 
 
 
 
 The backend compile entry point that
direct netplist authoring supplies rather than bypasses. 
 
 
 
 
 ANECompiler 
 
 
 
 The single compiler binary that lowers the front IR to the
backend IR and then to task descriptors for every target, so one host
can construct any of the 28 targets’ hardware-abstraction blobs. 
 
 
 
 
 ANECompilerService 
 
 
 
 The out-of-process compile service;
repeated failed compiles in quick succession can stall it, so pace
compiles after a failure by about 15 seconds, covered in Part V. 
 
 
 
 
 ANEServices 
 
 
 
 The user-space framework layer beneath the runtime that
marshals requests into IOKit calls. 
 
 
 
 
 AppleH11ANEInterface 
 
 
 
 The kernel driver for the engine,
decompiled at version 9.511.3, that holds the IOKit class hierarchy and
the user client. 
 
 
 
 
 ASC_CHINOOK 
 
 
 
 The firmware’s internal chip codename string for the H13
ANE coprocessor. 
 
 
 
 
 bridge ops 
 
 
 
 Hidden backend layer kinds reached by
direct netplist authoring, such as fused attention, fused rank, and
fused rearrange, each paired with one frontend bridge module, described
in Part II and cataloged in Appendix
 B . 
 
 
 
 
 CCDMA 
 
 
 
 The cross-chip and cross-engine DMA and event-sync engine; on
M1/H13 it is folded, and it is present natively on A15 and later and on
M5, where it enables resident state. 
 
 
 
 
 CSNE, CSNE_CMD_* 
 
 
 
 The host-to-firmware
command protocol, where CSNE_CMD_* are the numeric command
opcodes the host mailbox issues to the firmware. 
 
 
 
 
 DART 
 
 
 
 The ANE’s IOMMU, a 16 KB-page, 3.5 GiB-window unit that maps host
physical RAM into the engine’s device address space. 
 
 
 
 
 DPE 
 
 
 
 Dynamic Power Estimation: a firmware
activity-counter power estimate calibrated by 10 device-tree
coefficients and bounded by the peak-power ceiling. 
 
 
 
 
 DVA 
 
 
 
 Device Virtual Address: the address the engine issues, resolved by
DART to physical RAM, used interchangeably with IOVA. 
 
 
 
 
 dispatch floor 
 
 
 
 The fixed per-dispatch latency, about
0.23 ms on the M1 anchor and a fitted 0.11 ms on the M5, below which a
kernel cannot run regardless of its size, covered in Part III. 
 
 
 
 
 .e5 
 
 
 
 The compiled-program dispatch-layer container whose size
tracks the segment and dispatch count rather than the operation
count. 
 
 
 
 
 e5rt 
 
 
 
 The E5 runtime, the C API that the frontend uses
to load and stream programs and the unentitled reachable surface, which
still relays to aned underneath. 
 
 
 
 
 EIR, NitroIR 
 
 
 
 The runtime’s lowered IR, a Lisp-style S-expression node
tree serialized on disk, whose pivot type is the fp16
 ndarray<half> . 
 
 
 
 
 Espresso 
 
 
 
 Apple’s cross-backend neural-network runtime
and scheduler that hosts the E5 execution engine and the cost-model
placement segmenter. 
 
 
 
 
 ExeLoop 
 
 
 
 The firmware’s main control execution loop and finite-state
machine that fetches and dispatches task descriptors through the RUN,
IDLE, and EXEC states. 
 
 
 
 
 fp16 
 
 
 
 Half-precision IEEE float, the engine’s native
compute and storage type, with a maximum finite magnitude of 65504. 
 
 
 
 
 fp16 accumulator 
 
 
 
 A shorthand tag for the MAC numeric behavior: a
single wide accumulator of the fp32 class supplied by radix-4
fp16-rounded input tiles, where the only quantization is fp16 input and
partial rounding and the fp16 output grid. 
 
 
 
 
 fp8 (E4M3, E5M2) 
 
 
 
 The 8-bit float weight and activation
datapath, present only on H18, which decodes to fp16 before the MAC. 
 
 
 
 
 generation-tag 
 
 
 
 The hardware-abstraction blob’s generation byte at
offset 0x0 , holding the hex H-number, the decisive
discriminator between near-identical targets such as H16s and H17s. 
 
 
 
 
 GOC, DynamicGOC 
 
 
 
 Generate-Output-Channels, the dynamic
unit that generates the output-channel-group kernel tiles from a runtime
weight, present from M1 onward. 
 
 
 
 
 HAL 
 
 
 
 The Hardware Abstraction Layer: the per-target scalar and byte
blob that data-drives nearly all per-family behavior and is the source
of truth for capability, limit, and cost, detailed in Part IX. 
 
 
 
 
 .hwx 
 
 
 
 The fully lowered hardware-executable
container, the counterpart to the .e5 . 
 
 
 
 
 int4-LUT, palette weights 
 
 
 
 Palettized 4-bit weight compression, one of
the two formats that stream natively on M1/H13 (alongside the sparse
form) at about 2.37 times, where int8 and blockwise-affine instead fold
into the descriptor. 
 
 
 
 
 IOVA 
 
 
 
 IO Virtual Address: the device virtual address
DART produces from host physical RAM, on a 16 KB page over a 3.5 GiB
window. 
 
 
 
 
 KMEM 
 
 
 
 The on-chip working and scratch buffer the task descriptor sizes
for weights and tiles, gated at 64 KB at legalization and the basis of
the working-set threshold. 
 
 
 
 
 KV-cache (resident) 
 
 
 
 An on-device key and value cache
that stays resident across dispatches for decode, built on M1 with
 share_buffer rather than native state, covered in Part
VIII. 
 
 
 
 
 LUT 
 
 
 
 Lookup table, used both for piecewise-linear activation
approximation and for the palette of int4 weight compression. 
 
 
 
 
 MAC 
 
 
 
 Multiply-accumulate, the compute primitive whose
datapath is an fp16 multiply, radix-4 fp16-rounded input tiles, and one
wide accumulator of the fp32 class. 
 
 
 
 
 MIL 
 
 
 
 The Model Intermediate Language, the front IR in single-assignment
form that the compiler segments and lowers to the backend IR. 
 
 
 
 
 MLComputePlan 
 
 
 
 The model-framework introspection
surface that reports per-operation device assignment and a cost weight,
the readable view of the placement segmenter. 
 
 
 
 
 .mlmodelc 
 
 
 
 The compiled model bundle that pairs the runtime
net, shapes, weights, and the .hwx . 
 
 
 
 
 multi-die, AllReduce, AllGather 
 
 
 
 The multi-die
collective-communication layer present on the multi-die H14 through H18
Max and Ultra-class dies, not a base-class feature. 
 
 
 
 
 NE core 
 
 
 
 A neural-engine compute core; the per-family count decodes
from the HAL as base 4, then 8, 16, 32, or 64 by suffix, described in
Part IX. 
 
 
 
 
 NID 
 
 
 
 The firmware task-queue notification identifier
owned by the state machine, 8-bit and taking values 1 through 255. 
 
 
 
 
 OCG 
 
 
 
 The Output-Channel Group, the compiler’s output-channel tiling
unit sized to the accumulator file, where a larger group means fewer DMA
re-bases. 
 
 
 
 
 OC/cycle 
 
 
 
 The per-cycle output-channel throughput of
the MAC array, the roofline unit in the cost model. 
 
 
 
 
 Path-A 
 
 
 
 Direct netplist authoring, hand-writing the backend netplist to
reach hidden layer kinds, which supplies ANECCompile and so
cannot reach a lowering the backend rejects, covered in Part II. 
 
 
 
 
 palettization 
 
 
 
 Weight compression that maps each weight
to a lookup-table index, the int4 form of which streams natively on
M1/H13. 
 
 
 
 
 power domains 
 
 
 
 The five independently gated power domains of the H13
ANE, by which the engine modulates power through the number it
energizes. 
 
 
 
 
 PPL 
 
 
 
 Page Protection Layer: the kernel page-table
protection layer through which the ANE’s DART leaf writes go. 
 
 
 
 
 PPT 
 
 
 
 The peak-power ceiling and throttle under which the Dynamic Power
Estimation values are bounded. 
 
 
 
 
 pushTDList 
 
 
 
 The firmware function that hands a
task descriptor to the hardware and re-enters with an already-built
descriptor for resident chains. 
 
 
 
 
 roofline 
 
 
 
 The performance bound that takes the smaller of
compute-limited and bandwidth-limited rates as a function of arithmetic
intensity, the basis of the cost model in Part III. 
 
 
 
 
 RTBuddy 
 
 
 
 Apple’s coprocessor real-time-OS runtime
framework, the substrate the ANE firmware app runs on. 
 
 
 
 
 RTKit 
 
 
 
 The real-time-OS substrate beneath the ANE firmware, providing
the task and thread model and the synchronization primitives. 
 
 
 
 
 share_buffer 
 
 
 
 The runtime primitive that
aliases an output buffer to an input buffer after compile, giving a
zero-copy resident cache without native state. 
 
 
 
 
 slice × \times 16 saturation 
 
 
 
 An H13 codegen defect in which a slice with a
nonzero last-axis begin lowers to a scaled kernel that silently sends
values above 4094, which is 65504 / 16 65504/16 , to infinity; H13-only and
clean on H17. 
 
 
 
 
 SoC T-number 
 
 
 
 The SoC part number, such as T8103 for
the M1 base and T8142 for the M5 base, which maps to an ANE H-generation
through the board-type sequence. 
 
 
 
 
 sparse-binary, SparseFmt 
 
 
 
 The sparse-weight compute format, where the
weight has a binary sparsity mask; the mask-and-values form streams
natively on M1/H13, while the packed sparse-binary palette-index form is
absent from the M1 version-5 descriptor and present from A15 and M5. 
 
 
 
 
 SPTM 
 
 
 
 Secure Page Table Monitor: the kernel monitor
that, with the Page Protection Layer, governs page-table edits and
physical-frame ownership. 
 
 
 
 
 stack layers 
 
 
 
 The top-to-bottom software path from the frontend through
the runtime, the framework, aned , ANEServices, IOKit, and
firmware to silicon, in Part VIII. 
 
 
 
 
 styx 
 
 
 
 The firmware and chip codename for the M1/H13
ANE. 
 
 
 
 
 TD, task descriptor 
 
 
 
 The hardware work unit the firmware loads and the
engine executes: a register-image descriptor of DMA sub-blocks and
framing, emitted per generation from the compiler’s descriptor struct,
detailed in Part VII. 
 
 
 
 
 TileDMA, KernelDMA 
 
 
 
 The conv datapath DMA engines: the
kernel source streams weight coefficients, the tile source streams input
activation tiles, and the tile destination writes outputs. 
 
 
 
 
 TM, Tensor-Mover 
 
 
 
 The firmware tile-manager driver that moves tiles and
drives the texture layers. 
 
 
 
 
 TQ, task queue 
 
 
 
 The firmware queue the state machine
enqueues a program’s task-descriptor partitions into. 
 
 
 
 
 wide accumulator 
 
 
 
 The fp32-class running sum of the MAC, which holds
small addends rather than dropping them, so a sum of representable terms
stays near-exact, covered in Part III. 
 
 
 
 
 Winograd 
 
 
 
 The Winograd fast-convolution transform the
compiler can emit for small kernels, trading multiplies for
transforms. 
 
 
 
 
 Zin, ZinIr, ZinMir 
 
 
 
 The compiler’s internal class namespaces: the
IR-object layer, the mid-IR build layer, and the task-descriptor codegen
layer. 
 
 
 
 
 
 
 D.3 Family and silicon map 

 
 The relation M ⁡ ( n ) = H ⁡ ( n + 12 ) M(n)=H(n+12) is anchored at both ends, with the live
M1 reporting h13g and the M5 cost-model trees decompiled on the
M5 host reporting H17C and H17S . The compiler-family
index drives operation legality, and the per-target HAL drives codegen,
limits, and cost. Table   D.2 maps each marketing name to
its ANE generation, architecture string, compiler family,
generation-tag, and core counts; Part IX gives the full table. 
 
 
 Table D.2: The Apple chip marketing names mapped to ANE generation,
architecture string, compiler family, generation-tag, and core
counts. 
 
 
 
 
 
 Marketing name 
 
 
 
 ANE H-gen 
 
 
 
 OS arch string 
 
 
 
 Compiler family 
 
 
 
 generation-tag 
 
 
 
 NE cores by suffix 
 
 
 
 
 
 
 A13, M1 
 
 
 
 H13 
 
 
 
 h13 , h13g 
 
 
 
 A13 
 
 
 
 0x0d 
 
 
 
 4, 8
(g) 
 
 
 
 
 A14, M2 
 
 
 
 H14 
 
 
 
 h14 , h14g ,
 h14c 
 
 
 
 A14 
 
 
 
 0x0e 
 
 
 
 4, 8, 32 
 
 
 
 
 A15, M3 
 
 
 
 H15 
 
 
 
 h15 , h15g , h15c 
 
 
 
 A15 
 
 
 
 0x0f 
 
 
 
 4, 8, 32 
 
 
 
 
 A16, M4 
 
 
 
 H16 
 
 
 
 h16 , h16s 
 
 
 
 A16 
 
 
 
 0x10 
 
 
 
 4, 8, 16, 32 
 
 
 
 
 A17, M5 
 
 
 
 H17 
 
 
 
 h17 , h17s 
 
 
 
 A17 
 
 
 
 0x11 
 
 
 
 4,
8, 16 (M5), 32, 64 
 
 
 
 
 A18 
 
 
 
 H18 
 
 
 
 h18 
 
 
 
 A18 
 
 
 
 0x12 
 
 
 
 4 
 
 
 
 
 
 The M5 base is the h17 runtime arch and the H17s 
compiler target, the 16-core variant, not H16s. The suffixes g ,
 s , c , and d decode to NE-core counts of 8,
16, 32, and 64 from a single HAL field. A17 and A18 add no new operation
capabilities over A16 and scale only the core count; the A13 to A16 jump
was the last capability expansion. The fp8 datapath is H18 only. 
 
 
 
 
 Appendix E Provenance 

 
 This appendix records the evidentiary basis of every substantive claim
in the guide, Part by Part and chapter by chapter. The method is the one
given in the Methodology chapter: the engine was reached directly below
Core ML, the stack was read by static decompilation of the runtime,
compiler, kernel driver, and firmware, and values were taken by live
read-only instrumentation and by compile-and-run probing. Two silicon
points were measured directly, M1/H13 (Apple M1) as the primary host and
M5/H17s (Apple M5) as the second, with an A14-class part (Apple M2, H14)
as a middle point where a claim required one. Each claim below is marked
one of three ways: measured on a named generation, decompile-derived
from a named binary, or predicted from the per-chip tables and not yet
confirmed on silicon. 
 
 
 Part I. The Machine 

 
 Part I was measured on M1/H13 (Apple M1) unless a chapter notes
otherwise. 
 
 
 Chapter 1 . What
the ANE
is 

 
 Apple documents the engine only as the MLComputeUnits 
compute-unit selector at
developer.apple.com/documentation/coreml/mlcomputeunits, a placement
hint with no direct device API and no way to confirm which unit ran a
segment; this chapter extends that account by reaching the engine
directly below the selector. The roofline figures and the convolution
advantage over the GPU (3.8x faster, 9x more energy efficient) are
M1/H13 measured. The fp16-product and wide-accumulator result is
decompile-derived from the firmware and the compiler and confirmed by
the M1/H13 cancellation probe. The Core ML placement planner and the
direct Espresso route are decompile-derived. 
 
 
 
 Chapter 2 .
Execution
model 

 
 Apple documents only the load-and-predict surface ( MLModel ,
 prediction(from:) ); the autonomous-coprocessor model in this
chapter, with its command mailbox, walked segment graph, and resident
state across dispatches, has no public counterpart and is reported as
reverse-engineered. The compile-once, dispatch-many split and the
disk-cached program are decompile-derived and confirmed by M1/H13
dispatch tracing. The mailbox-and-doorbell command channel, the
autonomous controller, operand mapping through the address-translation
unit, and the walked segment graph with its static-control-flow
consequence are decompile-derived from the firmware, kernel-driver, and
program-format work. The resident-state mechanism through
output-to-input buffer aliasing is M1/H13 measured, observed to persist
and update an accumulator and a key-value cache across successive
dispatches with no host resubmission. 
 
 
 
 Chapter 3 .
Numerics 

 
 The fp16 datapath and the type limits are decompile-derived from the
firmware and the compiler, with the activation-table coefficients read
out of the compiler binary constant section. The wide accumulator and
its radix-4 first stage, activation-table behavior and the
twenty-three-op accuracy sweep, NaN coercion and the gelu and swish
origin biases, round-half-to-even output grid, MAC saturation at exactly
 2 15 2^{15} , denormal handling, softmax max-subtraction, and
bit-deterministic output for a fixed graph and input are all M1/H13
measured. The slice saturation threshold at 4094 is M1/H13 measured and
reproduced on A14/H14 (Apple M2), where 4094 stays finite and 4096
overflows; the clean route arrives at A15 and later. The
cross-generation accumulator behavior holds family-wide, the M5/H17s
difference being a one-unit-in-the-last-place scheduling and tiling
reorder rather than an accumulator-width change. Denormal preservation
inside the M5/H17s accumulator, where the M1 flushes to zero inside the
multiply-accumulate, is M5/H17s measured and generational. Apple’s
conversion tooling documents low-precision compression at
apple.github.io/coremltools, and the int8 relation here agrees with its
affine form w = s ⁡ ( q − z ) w=s\,(q-z) ; the wide-accumulator and per-product
cancellation results have no public counterpart and are reported as
reverse-engineered. 
 
 
 
 Chapter 4 .
Capability
surface 

 
 The native classes, type limits, compile-legal envelope, and M1 limits
are M1/H13 measured by operation-conformance runs, each native operation
compiled and run and each unsupported one rejected on device. The
attested-is-not-reachable rule is M1/H13 measured: three-dimensional
convolution fails backend lowering on every device mask despite its
capability byte, and the top-k, sort, and dynamic-slice validators are
callable but code-generation-rejected on the M1. The cumsum result is
M1/H13 measured through the curated runtime path, correcting the earlier
no-path status. The unsupported-on-every-family set and the per-family
unlock points for the texture-engine operations, sin and cos, and the
rank and sort bridge are decompile-derived from the operation floors and
validators and confirmed on the M1 only at its boundary; the chip that
first runs each is predicted from the floor table. Apple documents the
convertible operation set at apple.github.io/coremltools and
developer.apple.com; this chapter extends and partly corrects it,
reporting what compiles and runs on the direct path rather than what the
public converter accepts, since some accepted operations, such as
three-dimensional convolution, do not lower to the engine. 
 
 
 
 
 Part II. Reaching the ANE 

 
 Part II was measured on M1/H13 (Apple M1) unless a chapter notes
otherwise, with chapter 7 also
measured on M2/H14 (Apple M2 Pro) and M5/H17s (Apple M5). 
 
 
 Chapter 5 .
Software
stack 

 
 Apple documents the compute-unit selector, model loading, and the
placement read-out ( MLComputePlan.load ,
 deviceUsage(for:) , estimatedCost(of:) ) at
developer.apple.com/documentation/coreml, and that read-out agrees with
the segmenter decision reported here; the layered runtime beneath it and
its internal cost graph are not documented and are reported as
reverse-engineered. The layering and the runtime’s ownership of compile,
library, stream, and descriptors; the shortest-path placement segmenter
with its per-operation-by-backend cost graph, learned decision trees,
and launch and transfer penalties; the broker model with its single
privileged device gate, content-hashed program cache, and time-shared
request queue; the 292-export runtime surface and its options
dictionary; and the per-inference submit through
 IOConnectCallAsyncMethod selector 2 with the daemon’s lifecycle
selectors 3 through 6 are decompile-derived from the framework, runtime,
and daemon binaries. The reachability of the runtime below the
framework, with no placement planner and no entitlement for accepted
operations, is decompile-derived and confirmed by M1/H13 dispatch
tracing. 
 
 
 
 Chapter
 6 . Dispatching without Core
ML 

 
 Apple documents only the indirect MLModel and
 prediction(from:) route; the direct compile, load, bind, and
dispatch route here is reported as reverse-engineered and extends that
account with a planner-free path that targets the engine on purpose. The
five-step workflow and the absence of a placement planner are
decompile-derived from the runtime and the format pipeline. The absence
of an entitlement requirement for accepted operations is
decompile-derived and confirmed M1/H13 measured from ordinary user
space, and the single-submission multi-step drive with its
performance-neutral result and the resident-state buffer aliasing it
rests on are M1/H13 measured. 
 
 
 
 Chapter
 7 . Weights and
compression 

 
 This chapter measures across three endpoints: M1/H13 (Apple M1), A14 on
M2/H14 (Apple M2 Pro), and M5/H17s (Apple M5). The int4 and sparse
streaming speedups and byte ratios, the int8 matmul latency and
weight-byte halving, and the M1 folding of the int8 and blockwise forms
are M1/H13 measured. The A14 int8 and sparse stream and the A14
blockwise fold are M2/H14 measured, and the streaming of all four forms
is M5/H17s measured. The weight-reconstruction codecs and the per-format
hardware-abstraction-layer streaming gates are decompile-derived from
the ANE compiler; the A15 floor at which the blockwise form first
streams is predicted from the gate pattern and not yet
silicon-confirmed. Apple’s conversion tools document palettization,
quantization, and pruning at apple.github.io/coremltools as a model-size
feature; this finding extends that account, showing the same forms
stream on the unentitled engine for a bandwidth gain. 
 
 
 
 Chapter 8 .
Entitlement
boundary 

 
 The four gated features and the layer each gate is at are M1/H13
measured: three-dimensional convolution fails backend lowering on every
device mask, a native-state program fails the compile with the
counter-and-event engine stubbed in the M1 descriptor, a bf16 input or
output fails with an unsupported-dtype rejection and is absent from the
eleven-code program-I/O enumeration, and a symbolic dimension parses but
fails to lower. The framework cast of bf16 to fp16 and the bucketed
fixed-shape handling of flexible shapes are decompile-derived from the
framework and system bundles, and the load-time signature boundary is
decompile-derived from the kernel driver’s corecrypto signature and
trustcache vnode-trust checks, with the load rejection code
 0xe00002e2 observed on the M1. The arrival of native resident
state on a later generation is predicted from the per-family hardware
descriptor and not measured on that silicon. Apple documents these
capabilities (flexible shapes, the MLState type) at the
conversion and runtime layer; the finding shows they are not reachable
on the unentitled direct path, correcting the impression that a
documented capability runs on the engine directly. 
 
 
 
 
 Part III. Performance and
Fit 

 
 Part III was measured on M1/H13 (Apple M1; M1 Max), with a second pass
on M5/H17s (Apple M5) and an A14-class middle point on M2/H14 where a
cross-device or cross-generation claim required it. Apple publishes no
roofline, no per-workload power or efficiency figures, and no
cross-processor comparison for the engine, so the figures across this
Part are reported as measured rather than against a documented account. 
 
 
 Chapter 9 .
Roofline 

 
 The M1 compute and bandwidth ceilings, the 141 FLOP-per-byte ridge
point, 2 MB working-set threshold, 0.23 ms dispatch floor, and
conv-throughput scaling are M1/H13 measured from the memory-controller
and energy counters and end-to-end timing. The saturating-method figures
(the large-matmul compute ceiling, effective peak, wall-clock
weight-stream bandwidth matching the compiler’s internal 50 GB/s
constant, int8 rate, and full-call floor) are M1/H13 measured live in a
read-only dtrace session, and are presented alongside the counter-based
and slope-based figures with the methodology difference noted. The
cross-device ridge points, the standalone and weight-stream bandwidths,
and fused-block rate are M5/H17s measured. The fusion-and-floor model is
decompile-derived from the analytic cost model and fit to the measured
M1 convs within plus or minus 17 percent; cross-chip scaling of the
ceilings is predicted from that model, not asserted as a measured M1
fact. 
 
 
 
 Chapter
 10 . Power and
efficiency 

 
 The convolution-stack efficiency figures, the absolute-power comparison
on the 4096 matrix multiply, the 2-to-14-times efficiency range, and
sustained-load behavior are M1/H13 measured, with package power from
hardware instrumentation. The power-utilization model (the zero idle
rail, dispatch floor, fp16 and int8 compute-bound draw, regime-dependent
points, and operations-per-watt optimum near 0.37 pJ per FLOP) is M1 Max
measured with the root power sampler, which exposes only a power reading
and a binary on-or-off state, with no frequency or voltage telemetry.
The A14-class middle generation is measured on that silicon, and the M5
efficiency figures are M5/H17s measured. 
 
 
 
 Chapter 11 .
ANE, GPU, and
CPU 

 
 The per-class speed and energy verdicts are M1/H13 and M5/H17s measured
by a single sixteen-class harness recording minimum latency,
idle-subtracted total-package power, and fp16 relative error per class.
The saturation peaks, the large-N matrix-multiply falloff, and serving
crossovers are M5/H17s (Apple M5 Pro) measured; the per-eval overhead
floor and the M1 power gap are M1/H13 measured. 
 
 
 
 Chapter
 12 . Across the chip
family 

 
 The naming rule M ⁡ ( n ) → H ⁡ ( n + 12 ) M(n)\rightarrow H(n+12) is decompile-derived from
the per-family device tables and confirmed on the measured parts: M1/H13
by the live h13g architecture string, M2/H14g on the live A14 host, and
M5/H17s by the resolved target. The family-wide operation limits and the
core-and-clock scaling are decompile-derived from the operation floors
and the per-target scalar tables. The M5 throughput and working-set
threshold, the ten-of-ten cross-silicon prediction pass, the
M1-versus-M5 training and inference parity (0.9080 against 0.9070,
deterministic across runs), and the one-unit-in-the-last-place fp16
divergence bound are M5/H17s and M1/H13 measured; the M2 campaign
measured training accuracy, the four fp16 axes, peak throughput,
compression, and the per-op max-dim caps on A14 silicon. The A15 and A16
generations and their M3 and M4 counterparts are decompile-derived from
the device tables and not individually measured, the A15/M3 rail being
the one generation that remains unmeasured. Apple’s product
specifications publish a marketing core count per chip, for example a
16-core engine, a different quantity from the four physical compute sets
measured on the M1; the H-architecture naming, the mapping, and
per-family gates are reported as reverse-engineered. The M5
single-program matmul peak of about 9.5 fp16 TFLOP/s and the
weight-stream bandwidth of about 145 GB/s over two DRAM read channels
are M5/H17s measured. 
 
 
 
 
 Part IV. Workloads 

 
 Part IV was measured on M1/H13 (Apple M1 Max) and M5/H17s (Apple M5
Pro), with an A14-class point on M2/H14 where noted, each figure marked
for the generation it was taken on. 
 
 
 Chapter
 13 . Vision, convolution, and
encoders 

 
 The convolution speed and efficiency, the convolution-stack and roofline
figures, the power gap, and per-eval floor are M1/H13 measured; the M5
convolution-stack, ResNet-18, twelve-layer-encoder, and
single-sentence-encoder ratios and the serving crossovers are M5/H17s
measured. The convolution lowering, Winograd gate, 2 MB working-set
constant, per-output-channel fold, and texture-engine operation set with
its single A14 family gate are decompile-derived from the ANE compiler
and the per-chip parameter table. The Q.4 crop-scale saturation
threshold, where 4094 × 16 = 65504 4094\times 16=65504 reaches the fp16 ceiling, is
decompile-derived and confirmed by the fp16 range probe on M1/H13 and on
A14 (M2); the clean route arrives on A15 and later. Apple documents
vision and image models on the engine only through the compute-unit
selector (developer.apple.com/documentation/coreml,
developer.apple.com/documentation/vision), with no direct datapath API
or cross-processor figures; this chapter extends that account with the
measured economics against the GPU and names the texture-engine
preprocessing path the public surface does not expose. 
 
 
 
 Chapter 14 . LLM
case
study 

 
 The per-eval dispatch floor, int8-hybrid result, and resident-cache step
are M1/H13 measured, the last by a two-proof resident-buffer probe; the
batched-decode comparison, the per-projection placement table and
position rule, and the speculative-decoding and batched-prefill serving
controls are M5/H17s measured. The dispatch and resident-state machinery
of the direct path is decompile-derived from the runtime, including the
output-to-input buffer aliasing that holds the cache resident, the
in-flight cap of 127, and per-process loaded-program cap near 128 (the
next load returns GetANEFModel: must re-compile ). Apple does
not publish engine-versus-GPU decode measurements, so the per-batch
decode verdict is reported as measured. 
 
 
 
 Chapter
 15 . Training on the
engine 

 
 The gradient audit, differentiable-vocabulary correctness to a cosine of
 1.0000 1.0000 , conv weight-gradient saturation threshold, M1 training
accuracy and loss-scale curves, and two-generation parity (0.9080 on M1
against 0.9070 on M5 for the identical seeded network) are M1/H13 and
M5/H17s measured. The width-axis slice saturation, exact at loss scale
384 and first overflowing at 512 above 65504 / 16 ≈ 4094 65504/16\approx 4094 , was
reproduced on A14 (M2), locating the clean route on A15 and later. The
absence of an engine-native backward operation is decompile-derived from
the shared compiler, which has gradient operations only in the
graphics-processor dialect. Apple documents on-device model update at
developer.apple.com/documentation/coreml, a limited fine-tuning surface
whose backward pass runs off the engine; this chapter extends that
account with a full forward, backward, and optimizer loop running as
engine graph operations, optimizer state resident across steps. 
 
 
 
 Chapter
 16 . Numerical and
scientific
computing 

 
 The iterative-solver envelope, the size bounds on the unrolled
factorizations, the full-spectral-decomposition relative errors, and
wide-accumulator behavior are M1/H13 measured, with the fused five-point
stencil margin measured on M5/H17s and the DFT-as-matmul throughput on
the M2 generation at N = 1024 N=1024 . The static-dataflow constraint and
the absence of data-dependent control flow are decompile-derived from
the operation set and the compiler. The fp16-clean DFT bound near
 N = 2048 N=2048 is predicted from the wide-accumulator reduction and the
fp16 rounding of the matrix entries, an edge of the representable range
consistent with the accumulator measurements rather than a single
measured cutoff. Apple documents dense linear algebra and signal
processing through the accelerate framework at
developer.apple.com/documentation/accelerate, all targeting the CPU
rather than the engine; this chapter maps which of those kernels fit the
engine and which are architecture-limited, a mapping the public
documentation does not provide. 
 
 
 
 
 Part V. Practice 

 
 Part V was measured on M1/H13 (Apple M1), with M5/H17s (Apple M5) as the
cross-chip reference where a second generation is needed. 
 
 
 Chapter 17 .
Model-design
rules 

 
 The tensor-dimension boundaries, the convolution kernel and stride
limits, the arg-min and arg-max 2048 cap, and pooling-window behavior
are M1/H13 measured, swept until compile flipped from accept to reject.
The per-operation validators, the kernel-format and maximum-dimension
fields, the divisibility checks, and working-set and kernel-memory
budgets are decompile-derived and joined to those sweeps; the per-family
unlock points for the texture-engine padding modes, the
square-after-reduction mode, and sin and cos are decompile-derived from
the per-chip support flags, confirmed on the M1 only at its boundary and
predicted for the chip that first enables each. On the public side,
Apple documents the conversion-time constraints and supported converter
configurations at apple.github.io/coremltools; this chapter reports the
argument, shape, and mode limits the on-device validators enforce, which
the public converter does not enumerate. 
 
 
 
 Chapter
 18 . Optimization and the
cost
model 

 
 The convolution latency fit and the dispatch floor are M1/H13 measured
(Apple M1; M1 Max), and the cross-chip bandwidth, floor, and peak re-fit
are M5/H17s measured, with the core-scaled bandwidth confirmed by direct
streaming at 57.5 GB/s against the M1’s 10.4 GB/s. The compiler’s
analytic cost functions (the cycles, roofline, and wall-time chain) are
decompile-derived with the per-chip parameters walked live from the
hardware-abstraction table; the cross-chip scaling of unmeasured targets
is predicted from core-count and clock ratios. The cost-model fidelity
is M1/H13 measured: a median error near 31 percent with 11 of 68 shapes
within plus or minus 17 percent, sound as an ordinal placement tool
rather than an absolute-latency oracle, with attention unmodeled and the
9.0 GB/s bandwidth anchor held below the roughly 40 GB/s effective rate
because it is jointly calibrated for the convolution fit. There is no
public counterpart: Apple does not publish the engine compiler’s cost
model or its per-chip parameters, so the model is reported here as
decompile-derived and validated against M1/H13 and M5/H17s measured
latency. 
 
 
 
 Chapter 19 .
Pitfalls and
limits 

 
 The slice-saturation threshold, dynamic-weight convolution batch
boundary, compile-failure back-off, and four-character-code lowering
limit are M1/H13 measured, and the A14 generation (M2) was measured to
saturate on the same slice, locating the clean route on A15 and above
and confirmed clean on the M5. The per-target slice-lowering template
and its DMA source-path and patch-width routines are decompile-derived,
giving the times-16 fixed-point DMA format and the target-keyed slice
route; the clean A15 route is decompile-derived from the per-family
lowering and confirmed clean on the M5, not measured on A15 silicon
directly. These are failure modes of the private compiler and have no
public counterpart: they are reported as measured on the M1 and
reverse-engineered from the compiler binary. 
 
 
 
 
 Part VI. The Silicon 

 
 Part VI was measured on M1/H13 (Apple M1; M1 Max, live architecture
string h13g ); the datapath geometry and memory hierarchy are
decompile-derived from the per-chip hardware-abstraction table and the
engine compiler, calibrated against the M1 anchors. 
 
 
 Chapter
 20 . Datapath and MAC
geometry 

 
 The core count of four, per-core throughput scaling of 1 to 4,
power-rail step per core, radix-4 fan-in, wide accumulator, and
output-channel-group pass-doubling threshold at 192 to 256 are M1/H13
measured. The accumulator budget of eight and the lane widths of four
and eight are decompile-derived and uniform across chips per the
hardware-abstraction table, which was carved from the H13 firmware blob
and calibrated at the core-count, cycle-divisor, and working-set
offsets; the convolution-lowering and performance-model functions are
decompile-derived from the ANE compiler
( GetNumOutputChannelsPerCycle ,
 GetNumOutputChannelsPerAccumulator , ComputeMaxOcgSize ,
 ZinMirNECoreAssignment , GetNumNeededNEsNextPow2 ).
Apple publishes a marketing core count per chip, for example a 16-core
M1, a different quantity from the decoded num_nes of four; the
multiply-accumulate geometry has no public counterpart and is reported
as reverse-engineered and measured. The int8 compile flag is weight-only
quantization that leaves the multiply-accumulate in fp16, neutral on
compute-bound work and about 1.5 times faster only on
weight-bandwidth-bound matmuls near a 4096-by-4096 weight, M5/H17s
measured. 
 
 
 
 Chapter 21 .
Memory
hierarchy 

 
 The 2.28 to 2.34 MB threshold and the 64-byte throughput period are
M1/H13 measured on the dispatch path, and the absence of a runtime
replacement policy is an M1/H13 measured negative, with sequential and
random re-reference order identical at every footprint. The field values
are decompile-derived: 0x1b8 (2 MB operand working set),
 0x1c8 (64 banks), 0x1c0 (16-byte granule),
 0x1f8 (2 MB stride ceiling), 0x1f0 (residency
threshold, 0 on M1), and 0x288 (64 KB kernel store); the
operand-size comparator, the bank function and conflict model, and
inverted residency-buffer gate are decompile-derived from the named
compiler routines, with the 2 MB boundary itself the operand-size
comparator. The A15-class, A16-class, and M5 values of field
 0x1f0 are read from the same table by offset but predicted for
those parts, the gate behavior confirmed on the M1 only. The memory
hierarchy, the bank function, and residency threshold have no public
counterpart and are reported as reverse-engineered and measured. The
compiler name for field 0x1b8 , MemCacheSize (also
 L2Size ) with its fl2-size override, is
decompile-derived; on the M5 the working-set crossing is smooth in
throughput and shows instead in DRAM energy per operation, bottoming
near a 2 MB operand, M5/H17s measured. 
 
 
 
 
 Part VII. The Toolchain and
Encoding 

 
 Part VII was measured on M1/H13 (Apple M1; M1 Max, live string
 h13g ), with chapter 25 
extending to M2/H14 (Apple M2 Pro) and M5/H17s (Apple M5). This Part is
mostly decompile-derived from the engine compiler decompile and its
constraint-string corpus, the per-chip hardware-abstraction table read
by byte offset across 28 target entries, and the runtime serializers and
task-descriptor setters; unless a chapter says otherwise, scalar
offsets, capability-byte offsets, struct fields, and symbol names are
decompile-derived. 
 
 
 Chapter 22 .
Compiler 

 
 The four-phase pipeline, task-descriptor partition budget,
allocation-type set, anec.matmul and anec.convolution 
lowerings, and fusion rules (the GOC fused unit, seven-slot epilogue,
fusable epilogues and the two-live-input, concat, and attention-cut
barriers) are decompile-derived from the engine compiler framework (the
9.509 build, a 4.1-million-line decompile) and the constraint-string
corpus. The validator export set, the per-layer reject strings, and the
code-generation rejections for top-k, sort, dynamic-slice, and
three-dimensional convolution are M1/H13 measured. The compiler
internals, the backend anec.* dialect, and the
 _ANECValidate* surface have no public counterpart and are
reported as reverse-engineered; the public tools document only the
frontend operation set and conversion passes. 
 
 
 
 Chapter
 23 . Program and container
format 

 
 The two-layer split, four-field root table, cast-inference-cast
operation shape, seven register groups, 15-bit and 17-bit dimension
widths, relocation-slot model, 44-byte sparse record, and the HWX
on-disk layout (the 0xbeefface Mach-O variant, the segment set,
the ZinAneTd linked list, the per-lane weight tiles, and shape
descriptors) are decompile-derived from the serializer and
task-descriptor symbols and cross-confirmed against the vendor’s
task-descriptor symbol table. The dispatch-descriptor schema was
validated by a round-trip through the schema compiler (version
25.12.19), which regenerated an object-API header and a binary
reflection schema without error. The decoded identity-linear program
with its segment map, port descriptors, register records, and weight
bank are M1/H13 measured, parsed byte for byte from real on-disk files
in the runtime caches, with the resolved tensor frame read from the
post-compile status sidecar. The format has no public counterpart and is
reported as reverse-engineered; the full FlatBuffer schema is Appendix
 C . The custom-bar
bit-field relocation, which patches a resolved value into a named
descriptor field by bit offset and width, and the range-checked live-in
shape and stride parameters that let one program serve a range of input
shapes, are decompile-derived from the program loader. 
 
 
 
 Chapter
 24 . HAL and capability
gates 

 
 The scalar offsets, the capability-byte offsets, and family floors are
decompile-derived, with every per-target constructor invoked on this
host (live string h13g ) to read byte-exact values for all 28
targets, joined to the minimum-family operation trait and tier
assignment read from the same binary. The per-family unlock generations
for the texture engine, sin and cos, and the dimension and format-count
steps are decompile-derived from the per-target tables and confirmed on
the M1 only at its boundary; the generation that first enables each is
predicted from the floor table. The attested-is-not-reachable rule is
M1/H13 measured: three-dimensional convolution has its HAL kernel-depth
attestation at offset 0x70 and fails backend lowering on every
device mask, and the top-k, sort, and dynamic-slice validators are
callable but code-generation-rejected. The packed-bitfield struct
measures 0x938 bytes; its non-flag residual is the cost-model
coefficient block at 0x580 through 0x7f0 plus about
two soft fp64 coefficients, and the offsets past 0x938 , read in
an earlier round as an A12 operation-emulation catalog at 0xa30 
through 0xe84 , are a read into zeroed memory beyond the struct
and have no table; the capability-flag offsets are decompile-derived
from the ZinIrHalParameters reader symbols. The HAL table, the
capability-byte region, and minimum-family trait have no public
counterpart; Apple documents only the model framework and the
convertible operation set, not the per-chip capability table or the
per-operation family floor. 
 
 
 
 Chapter
 25 . Compression
internals 

 
 The bit-layout and address detail are M1/H13 (table-descriptor codegen
version five, family two, A13) unless another version or family is
named. The sparse and int4 speedups and byte ratios, the byte-identical
compiled program, and the M1 fold of the int8 and blockwise forms are
M1/H13 measured; the A14 int8 stream and blockwise fold are M2/H14
(Apple M2 Pro) measured; the all-forms-stream endpoint is M5/H17s (Apple
M5) measured. The kernel-format helper tables, affine and palette
dequantization codecs, dequantize-to-dense fold path, streaming and
palette gates, on-chip-memory budget caps, and Winograd eligibility gate
are decompile-derived, with the on-device sparse-format field read from
the register map; the A15 floor at which the blockwise form first
streams is predicted from the gate pattern, and the resident Winograd
transform matrices are predicted, their textbook forms matching the
engine’s behavior but not byte-confirmable from the binary. Apple’s
conversion tools document palettization, quantization, and pruning at
apple.github.io/coremltools as a model-size feature; this chapter
extends that account with the on-device codec arithmetic and the
per-family streaming datapath. 
 
 
 
 Chapter
 26 . Hidden
layers and direct netplist
authoring 

 
 The fused-attention, ranking, and spatial-rearrange layers were
authored, compiled, and dispatched on the M5/H17s byte-exact against a
host reference, and the M1 gates and the top-k forbidden band were
confirmed on the M1 (measured). The native layer-descriptor catalog, its
per-layer ZinParse<Name>Unit parsers and
 _ANECValidate<Name>Layer checkers, and
the constant-string constraint corpus are decompile-derived, joined to
the netplist schema read out of the runtime framework. On the public
side, Apple documents the model converter and its intermediate-language
operation set at apple.github.io/coremltools, which does not emit these
native layer kinds; this chapter authors them directly, the attention,
ranking, spatial-rearrange, geometry, and normalization descriptors
being present in the compiler and reachable through the network
description even though the converter never produces them. The 33-knot
activation-LUT format and the gated NeuronCustom netplist path
(a parser that requires and then rejects the same field sets) are
decompile-derived; the rectifier-basis reproduction of an arbitrary
pointwise function is M5/H17s measured. 
 
 
 
 
 Part VIII. System
Internals 

 
 Part VIII rests on M1/H13 (Apple M1; M1 Max, and the T6000-generation
engine where a multi-die part is needed), with an M2-class kernel cache
as the cross-generation reference where cited. Much of it is
decompile-derived static analysis with no firmware executed: the
unencrypted real-time-kernel preload executable is carved from the
on-package firmware image and read for its strings, asserts, and
disassembled handlers, and the kernel cache is read for its symbols,
dispatch arrays, and call sites. 
 
 
 Chapter
 27 . Kernel driver and IOKit
ABI 

 
 The two IOExternalMethodDispatch2022 arrays are M1/H13
measured, read byte for byte from the kernel cache’s read-only data
section and corroborated on an M2-class cache where all 26 size tuples
are byte-identical, and the control-client open and submit struct sizes
are cross-validated against captured user-space call blobs. The selector
handlers, four-layer call path, doorbell register write,
entitlement-check call sites for
 com.apple.ane.iokit-user-access and
 com.apple.ane.allow-dataChaining-access , driver class hierarchy
and device properties, and broker model are decompile-derived from the
unstripped kernel-cache symbols, kext property lists, live device
registry, and a system-wide entitlement sweep. The driver’s user-client
ABI has no public counterpart and is reported as reverse-engineered; the
IOKit user-client framework and the
 IOExternalMethodDispatch2022 structure are public, but this
driver’s selector numbers, struct sizes, and handler set are not. On the
M5 the client-creation gate ANEClientInfo::create , its
 copyClientEntitlement stamp of isPrivileged and
 allowDataChaining , and six further driver-enforced
 com.apple.ane and com.apple.private.ane entitlements
are decompile-derived from the M5 kernel driver. 
 
 
 
 Chapter
 28 . Address translation and
the
DART 

 
 The leaf word phys | 0x8000000000000000 , 16 KB
granule, active stream set {0, 1, 2} , translation-table
base 0x90022320 , and host-to-firmware rebase to the
 0x1bc4 aperture are M1/H13 measured read-only on the live
dispatch path (Apple M1 Pro, T6000-generation DART): the granule and
stream set from the live device tree, the base register from
function-boundary probes, and the leaf-word template, segment structure,
and protection classes from probes across 26178 leaf-map events. The
leaf-word bit layout, the fault-register offset map, the
panic-terminated fault path (panic confirmed M1/H13 from the disassembly
of every fault-path function), the IODARTErrorInfo descriptor
layout, the [engine+0xe028] status predicate, and firmware
rebase arithmetic with its three aperture-config offsets are
decompile-derived, the rebase arithmetic unicorn-verified. The
fault-capture register decode is predicted from the published controller
field layout and not measured, because a fault panics the machine. The
address-translation unit, its leaf entry format, the rebase boundary,
and the fault-capture block have no public counterpart and are reported
as reverse-engineered. The per-client isolation contexts, the eight
 mapper-ane0 translation mappers in the live IORegistry and the
 ANEIsoID1 through ID7 exclave capabilities that bind
them, are M5/H17s measured with System Integrity Protection enabled. 
 
 
 
 Chapter 29 .
Firmware 

 
 The preload executable is the M1-generation real-time-kernel image,
build identity RTKit-3255.120.11.release , chip tag
 ASC_CHINOOK . The task roster, priority bands, heap and pool
model, execution-loop command set, scheduler deadline, and fault
post-mortem layout; the command-record classes and their
 sCSneCmdProcedureCall* invariants; the doorbell-emit sequence
around bit 39 of S3_3_C15_C8_0 , host-notify site
 @0x4c890 , and engine-to-graphics-processor doorbell at
 0x2_0646_8000 ; the bring-up order, seven MMIO banks, RTBuddy
endpoint, and three scratch handshakes; and the per-run statistics
buffer with its header, per-engine descriptors, and host-side null gate
are decompile-derived from the embedded strings, assertion expressions,
and disassembled handlers. The firmware has no public counterpart and is
reported as reverse-engineered from the unencrypted image; Apple
documents only the model framework and conversion tools above this
layer, not the on-engine operating system. The CHINOOK control-CPU
register map, its eleven thread contexts, level-two cache, and pipeline
error-capture and power-down-save registers, is decompile-derived from
the kernel driver. 
 
 
 
 Chapter
 30 . Host-to-firmware
command
protocol 

 
 This chapter is static analysis of the unencrypted M1 firmware image, an
ARM64e real-time-kernel Mach-O, with no firmware executed. The command
vocabulary, numeric identifiers, header layout, and body bounds are read
from the ordered command-name string table, struct-size asserts, and log
format strings; header byte offsets are inferred from field order and
alignment, while field presence, widths, and bounds are read directly
from in-binary asserts. The 94-entry CSNE_CMD enumeration (93
dispatched command identifiers plus the invalid sentinel), the roughly
ten fast-path ids, and the seventy-six-slot dispatch vtable (arm64e
auth-rebase chained pointers in __DATA.__const , low
thirty-two bits giving the target, the procedure-call slot at
 +0x200 reaching 0x7374c and the inference slot at
 +0x190 reaching 0x74510 ) are decompile-derived. The
protocol, the command header, and CSNE_CMD_* vocabulary have
no public counterpart and are reported as reverse-engineered; the public
model framework describes application-level model loading, not the
controller command channel. The full numeric command table and the
decoded request structs are Appendix
 C . 
 
 
 
 Chapter 31 .
Power and
thermal 

 
 The clean 0 mW idle, the 176-second saturating loop holding flat power
and throughput under nominal thermal pressure, the first-op power-up tax
near 0.5 ms past a 100 ms idle gap, and the single held power state
across 56,527 dispatches are M1/H13 measured by read-only tracing. The
power-block base 0x2_6b8f_0000 , the opaque voltage base
 0x2_3b70_c008 , the five-store power-block arm, the
 0x11 peak-power control word, the engine and power-manager
device-tree nodes ( ane0@84000000 ,
 compatible "ane,t8020" , the 0x2_8400_0000 aperture,
the 0x2_8E08_0000 power-manager slice), the absence of local
DVFS, and firmware seven-step credit sequence are decompile-derived from
the H13 firmware Mach-O and live device-tree enumeration. There is no
public counterpart: Apple documents neither the power model, the fixed
operating point, nor the thermal behavior, so this account is reported
as reverse-engineered and measured. 
 
 
 
 Chapter
 32 . Security and
isolation 

 
 The cross-process timing side-channel (a 2.3 times latency jump under
contention and a 20 to 50 bit/s occupancy channel) and the intact data
isolation across 9000 concurrent results are M1/H13 measured. The
kernel-side trust boundary and its three program checks (code signature,
vnode trustcache, client code-signing identity), the firmware’s
structural-only check, and the secure and exclave method bodies (the
secure-mode transition state machine, the
 SwitchExclaveMode not supported stub, the inert
 mov w0, #0; ret exclave selectors) are decompile-derived
from the loaded kernel driver and the firmware image. There is no public
counterpart: Apple documents neither the secure and exclave transition
internals nor the cross-process isolation behavior, so this account is
reported as reverse-engineered and measured. On the M5 the exclave is
live rather than stubbed: the secure component
 com.apple.aneexclave , its capability-scoped segment access, and
the Tightbeam submit path are decompile-derived from the M5 exclave
bundle and boot kernelcache, with System Integrity Protection enabled. 
 
 
 
 Chapter
 33 . Telemetry and hardware
counters 

 
 On the Apple M1 and M1 Max, the readable whole-engine channels (DRAM
bytes, energy, clock residency), the signpost lifecycle, the all-zero
per-run output buffer, and forced-mask load rejection are M1/H13
measured. The ANEProgramCreateArgs layout, the +0x6c 
stats-mask offset, the twenty-four per-descriptor counter namespace, the
stats-buffer ABI 0x0201 , the initStatsBufferSection 
bail branch, and the free-running engine timebase counter at MMIO
 0x2_6b17_8000 (read by the firmware helper @0x30988 )
are decompile-derived from the runtime dylibs and the kernel driver.
There is no public counterpart: Apple documents none of the hardware
performance-counter block, per-task-descriptor namespace, stats-mask
enable, or firmware timestamp, so the block geometry, master enable,
readable-versus-walled split, and kernel gate are reported as
reverse-engineered and measured. On the M5 the gate actor (the
 aned daemon forcing statsMask=0 for a
 ThirdPartyAppUsingANE client), the per-channel
 DCS BW / ANE L0 and L1 State-residency bandwidth
histograms readable on the unentitled path, and the fuller
 ANE_THROTTLE_* and VDD_DRAM_VOLTAGE_CHANGE 
trigger family are M5/H17s measured with System Integrity Protection
enabled. 
 
 
 
 
 Part IX. Cross-Silicon
Reference 

 
 Part IX was measured on M1/H13 (Apple M1; M1 Max) with M5/H17s (Apple
M5) as the cross-chip reference; the work is decompilation and static
analysis of the one engine compiler binary across its full target set,
with boundaries reproduced on silicon where a part was in hand. 
 
 
 Chapter
 34 . Cross-silicon
targets 

 
 The 28-target set is measured, extracted by invoking each
per-architecture builder on the M1 (host chip irrelevant) and resolving
the M5 to H17s and the M1 Max to H13G by
fixed-build-directory compile. The target names, the suffix-to-core
decode at HAL offset 0x238 , the interchange-format tables at
HAL offset 0x658 , and four-byte format decode are
decompile-derived; the A14, A15, A16, and A18 targets and their M-series
counterparts are decompile-derived from the per-target tables and not
individually measured, and the M ⁡ ( n ) → H ⁡ ( n + 12 ) M(n)\rightarrow H(n+12) mapping is
confirmed only at the M1 and M5 ends with the middle generations
predicted. On the public side, Apple’s product specifications publish a
marketing core count per chip, for example a 16-core engine, a different
quantity from the decoded num_nes , which counts per-die
compute sets: four on the base M1 against the published sixteen. The
28-target compiler set, the H-architecture naming, the suffix-to-core
decode, and interchange tables are not publicly documented and are
reported as reverse-engineered. 
 
 
 
 Chapter
 35 . Per-family code
generation 

 
 The slice-saturation threshold, the top-k, sort, and dynamic-slice
code-generation rejections, and the operation decompositions are M1/H13
measured; the clean slice route and the native crop-resize, resample,
and trig operations are M5/H17s measured. The family enum,
 MinimumFamily<N> trait and its four
operation tiers, per-chip hardware-abstraction offsets, task-descriptor
patch-width path, and
 ConvertSlice<Family> lowering are
decompile-derived from the engine compiler framework (the 9.509 build,
87,874 functions); the A14 and A15 unlock points, M-series families
above the M1, and dedicated A15 code-generation branch with its cost
table, 45-operation floor, full H15 targets, and YUV420 input are
decompile-derived and not measured on A15 silicon. The family enum,
minimum-family trait, per-chip parameters, and per-family route
selection have no public counterpart; the public conversion tools
document the frontend operation set, optimization passes, and
compute-unit selector, not the backend per-family lowering reported
here. 
 
 
 
 Chapter
 36 . Predicted upper
tier 

 
 The fp8 format converters, E4M3 overflow enumeration, format-register
encoders, double-multiply gate, collective dialect operation set,
device-mesh and sharding lowering, reduction-to-atomic map, and
collective direct-memory-access emitter are decompile-derived, with the
family gates read from the 28-target capability bytes; the 64-core
ceiling, fp8 e4m3 and e5m2 datapath, and Ultra
device-mesh collective are decompile-derived and not measured on the
upper-tier parts. The E4M3 native multiply, accumulation, and saturation
(inferred from the encoders and the H18-only capability byte at offset
 0x52d ), the fp16 accumulation of an fp8 multiply (from the
absence of any fp8 accumulator field), and the running collective (the
enable byte at offset 0x48b zero on all 28 targets and the
register encoding stubbed on every family) are predicted, with no
current family materializing the collective. That the load-balancer
supports up to four engine dies while the M1 and M1 Max each register a
single engine, so cross-die steering engages only on a multi-die part
such as the Ultra, is M1 Max measured by the device registry. The fp8
datapath and the multi-die collective layer have no public counterpart
in Apple’s documentation and are reported as reverse-engineered and
explicitly unmeasured. 
 
 
 
 
 Back matter 

 
 The back-matter chapters rest on M1/H13 as the primary host and M5/H17s
for cross-generation scaling. 
 
 
 Methodology 

 
 Apple documents the engine only as a compute-unit selector at
developer.apple.com/documentation/coreml/mlcomputeunits, with no direct
device API; this chapter extends that account by reaching the engine
directly below the selector and characterizing it by static analysis and
live instrumentation. The direct dispatch route, the four
static-analysis artifacts, and the program-binary capture are
decompile-derived and confirmed by the kernel trace; the roofline
figures and the compile-service rate condition are M1/H13 measured, and
the cross-generation scaling and bounded numeric drift are M5/H17s
measured. 
 
 
 
 Open questions 

 
 The decoded baseline and the boundary limits are M1/H13,
decompile-derived from the compiler, hardware-abstraction tables, kernel
driver, and firmware and joined to live instrumentation; M5/H17s
confirmed the cross-family predictions. The M3/H15 and upper-tier
runtime behavior is predicted, decompile-derived from the gates and not
confirmed on silicon. 
 
 
 
 
 Appendices 

 
 The reference tables are decompile-derived from static, read-only
analysis of the M1/H13 binaries: the ANE compiler
( ANECompiler 9.509 ), its per-family operation-floor tables,
its per-layer validators and parsers, the host runtime, and the
unencrypted firmware image ( h13_ane_fw_styx_j5x.im4p ), with
no firmware executed and no engine jobs run. Where a value or status is
measured rather than decompile-derived, it was confirmed on physical
silicon, primarily M5/H17s and M1/H13, by compiling and dispatching
against a host reference. 
 
 
 Appendix
 A . The
operation-by-device
matrix 

 
 The M1, M2, and M5 columns are measured by operation-conformance runs,
each native operation compiled and run and each no-path one rejected on
device; the M3 column and the M4 part of the merged M4-and-M5 column are
decompile-derived predictions from the per-chip tables. The per-family
unlock points for the texture-engine operations, sin and cos, rank and
sort bridge, argument reductions, and weight-stream gates are
decompile-derived from the operation floors, validators, and
symbol-resolution map and confirmed on the M1 only at its boundary; the
family that first runs each is predicted from the floor table. Apple
documents the convertible operation set at apple.github.io/coremltools
and developer.apple.com; this table extends and partly corrects that
account, reporting what compiles and runs on the direct engine path,
since some accepted operations, such as three-dimensional convolution,
do not lower to the engine. 
 
 
 
 Appendix
 B . The hidden-layer
catalog 

 
 Each layer’s Type tag, descriptor symbol, and Params 
key set are decompile-derived from the compiler export table, parser
disassembly, constant-string key atlas, per-layer
 ZinParse<Name>Unit parsers and
 _ANECValidate<Name>Layer checkers, and
descriptor-initializer routines
 _ANEC<Name>LayerDescInitialize , joined
to the netplist schema read out of the runtime framework. The
fused-attention operand contract, the spatial-rearrange channel
ordering, the float16-bit-pattern convention for Alpha ,
 Epsilon , and Scale , and point-cloud output contracts
are M5/H17s measured by authoring and dispatching the layers, and the M1
arch gates, the Sort and DynamicSlice rejections, and
the top-k { 3 , 4 } \{3,4\} forbidden band are M1/H13 measured. Apple
documents the model converter and its intermediate-language operation
set at apple.github.io/coremltools, which does not emit these native
layer kinds; this catalog authors the native descriptors directly
through the network description. 
 
 
 
 Appendix
 C . Decoded reference
tables 

 
 Every value is read out of an M1/H13 binary by static analysis, with no
firmware executed: the attribute and opcode integers and IOKit struct
layouts from the compiler decompile ( ANECompiler 9.509 ) and
the host runtime; the error constants, command table, and tunable table
from the unencrypted firmware image
( h13_ane_fw_styx_j5x.im4p ) and the standard IOKit return
macros; the register map from the compiler’s task-descriptor setters and
getters; and the .e5 schema from the runtime serializer
symbols, validated byte-for-byte against a captured sample. The runtime,
firmware, compiler, and ABI surface consolidated here is private and
undocumented and is reported as reverse-engineered; the public model
framework, conversion tools, and intermediate-language reference
describe none of these numeric tables. 
 
 
 
 
 
 References 

 
 
 1. 
 
 AmiraniLabs. “libane: a
native Apple Neural Engine runtime.” Repository,
 https://github.com/AmiraniLabs/libane . 
 
 2. 
 
 Apple. Accelerate
and BNNS documentation.
 https://developer.apple.com/documentation/accelerate . 
 
 3. 
 
 Apple.
Active installed base of 2.5 billion devices, reported by T. Cook on
the first-quarter fiscal 2026 earnings call, January 29, 2026.
apple.com. 
 
 4. 
 
 Apple. Apple silicon
technical specifications. https://www.apple.com/mac/compare/ . 
 
 5. 
 
 Apple. Core ML
framework documentation.
 https://developer.apple.com/documentation/coreml . 
 
 6. 
 
 Apple. Core ML
Tools (coremltools) documentation.
 https://apple.github.io/coremltools . 
 
 7. 
 
 Apple. Vision
framework documentation.
 https://developer.apple.com/documentation/vision . 
 
 8. 
 
 Apple Machine
Learning Research. “Deploying Transformers on the Apple Neural
Engine.” Apple Machine Learning Research article, 2022. 
 
 9. 
 
 Benazir, A., and Lin,
F. X. “Efficient Mixture-of-Experts LLM Inference with Apple Silicon
NPUs.” Preprint,
 arXiv:2604.18788 , 2026. 
 
 10. 
 
 Bi, Z., Chen, X., Sun, L.,
Yao, Y., Shen, Q., Lou, J., and Deng, C. “RooflineBench: A
Benchmarking Framework for On-Device LLMs via Roofline Analysis.”
Preprint, arXiv:2602.11506 ,
2026. 
 
 11. 
 
 Bryngelson, S. H.
“ANEForge: Python for direct computation on the Apple Neural
Engine.” Preprint,
 arXiv:2606.17090 , 2026. 
 
 12. 
 
 Chen, L., Feng, D., Feng,
E., Wang, Y., Zhao, R., Xia, Y., Xu, P., and Chen, H.
“Characterizing Mobile SoC for Accelerating Heterogeneous LLM
Inference.” ACM SIGOPS Symposium on Operating Systems Principles
(SOSP), 2025.
 arXiv:2501.14794 , DOI
10.1145/3731569.3764808. 
 
 13. 
 
 Choi, J. W., Bedard, D.,
Fowler, R., and Vuduc, R. “A Roofline Model of Energy.” IEEE
International Symposium on Parallel and Distributed Processing
(IPDPS), 661-672, 2013. DOI 10.1109/IPDPS.2013.77. 
 
 14. 
 
 Community Apple Neural
Engine reverse-engineering repositories. johnmai-dev/ANE-LM,
mechramc/Orion, skyfallsin/apple-neural-engine-field-guide, and
dmaynor/apple-vuln-research. Repositories. 
 
 15. 
 
 Ding, N., and Williams,
S. “An Instruction Roofline Model for GPUs.” IEEE/ACM Performance
Modeling, Benchmarking and Simulation of High Performance Computer
Systems (PMBS), 7-18, 2019. DOI 10.1109/PMBS49563.2019.00007. 
 
 16. 
 
 Fanariotis, A.,
Orphanoudakis, T., and Fotopoulos, V. “Evaluating the Energy
Efficiency of NPU-Accelerated Machine Learning Inference on Embedded
Microcontrollers.” Preprint,
 arXiv:2509.17533 , 2025. 
 
 17. 
 
 Gerganov, G.
“whisper.cpp: Whisper inference in C/C++ with Core ML Neural Engine
support.” Repository, https://github.com/ggml-org/whisper.cpp . 
 
 18. 
 
 Hollemans, M. “The
Neural Engine: What Do We Know About It?” Community-maintained
repository, https://github.com/hollance/neural-engine . 
 
 19. 
 
 Hotz, G., and the tinygrad
authors. “tinygrad.” Repository,
 https://github.com/tinygrad/tinygrad . 
 
 20. 
 
 Hübner, P., Hu, A.,
Peng, I., and Markidis, S. “Apple vs. Oranges: Evaluating the Apple
Silicon M-Series SoCs for HPC Performance and Efficiency.” Preprint,
 arXiv:2502.05317 , 2025. 
 
 21. 
 
 Ignatov, A., Timofte,
R., Kulik, A., Yang, S., Wang, K., Baum, F., Wu, M., Xu, L., and Van
Gool, L. “AI Benchmark: All About Deep Learning on Smartphones in
2019.” Preprint,
 arXiv:1910.06663 , 2019. 
 
 22. 
 
 Ilic, A., Pratas, F., and
Sousa, L. “Cache-Aware Roofline Model: Upgrading the Loft.” IEEE
Computer Architecture Letters, 13(1), 21-24, 2014. DOI
10.1109/L-CA.2013.6. 
 
 23. 
 
 Jayanth, R., Gupta, N.,
and Prasanna, V. “Benchmarking Edge AI Platforms for
High-Performance ML Inference.” Preprint,
 arXiv:2409.14803 , 2024. 
 
 24. 
 
 Jouppi, N. P., Young,
C., Patil, N., Patterson, D. A., et al. “In-Datacenter Performance
Analysis of a Tensor Processing Unit.” International Symposium on
Computer Architecture (ISCA), 1-12, 2017. Also
 arXiv:1704.04760 . 
 
 25. 
 
 Kumaresan, R. “Orion:
Characterizing and Programming Apple’s Neural Engine for LLM Training
and Inference.” Preprint,
 arXiv:2603.06728 , 2026. 
 
 26. 
 
 ML.ENERGY / Zeus.
“Programmatic Energy Consumption Measurement on Apple Silicon
(macOS).” Project issue report (#159), 2025. 
 
 27. 
 
 Moon, S., Cha, J., Park,
H., and Kim, J. “Hybe: GPU-NPU Hybrid System for Efficient LLM
Inference with Million-Token Context Window.” International Symposium
on Computer Architecture (ISCA), 808-820, 2025. DOI
10.1145/3695053.3731051. 
 
 28. 
 
 Plyenkov, B.
“Decoupling Machine Intelligence from Application in IoT Devices.”
Master’s thesis, Aalto University, 2019. 
 
 29. 
 
 Prashanthi, S. K.,
Sahoo, K. K., Saikia, A. R., Gupta, P., Joshi, A. V., Pansari, P., and
Simmhan, Y. “Pagoda: An Energy and Time Roofline Study for DNN
Workloads on Edge Accelerators.” Preprint,
 arXiv:2509.20189 , 2025. 
 
 30. 
 
 Singh, M. “Inside the
M4 Apple Neural Engine, Part 1: Reverse Engineering.” Blog post and
repository, 2026, https://github.com/maderix/ANE . 
 
 31. 
 
 Tummalapalli, P.,
Arayakandy, S., Pal, R., and Kundan, K. “LLM Inference at the Edge:
Mobile, NPU, and GPU Performance Efficiency Trade-offs Under Sustained
Load.” Preprint,
 arXiv:2603.23640 , 2026. 
 
 32. 
 
 Verhelst, M., Benini,
L., and Verma, N. “How to Keep Pushing ML Accelerator Performance?
Know Your Rooflines!” IEEE Journal of Solid-State Circuits, 2025. DOI
10.1109/JSSC.2025.3553765. 
 
 33. 
 
 Williams, S.,
Waterman, A., and Patterson, D. A. “Roofline: An Insightful Visual
Performance Model for Multicore Architectures.” Communications of the
ACM, 52(4), 65-76, 2009. DOI 10.1145/1498765.1498785. 
 
 34. 
 
 Xu, D., Zhang, H., Yang, L.,
Liu, R., Huang, G., Xu, M., and Liu, X. “Fast On-device LLM
Inference with NPUs.” ACM International Conference on Architectural
Support for Programming Languages and Operating Systems (ASPLOS),
2025. arXiv:2407.05858 , DOI
10.1145/3669940.3707239. 
 
 35. 
 
 Yang, C., Kurth, T., and
Williams, S. “Hierarchical Roofline Analysis for GPUs: Accelerating
Performance Optimization for the NERSC-9 Perlmutter System.”
Concurrency and Computation: Practice and Experience, 32(20), e5547,
2020. DOI 10.1002/cpe.5547. 
 
 36. 
 
 Yoon, E. “ane: a
reverse-engineered Linux driver for the Apple Neural Engine, with
anecc.” Repository, 2022, https://github.com/eiln/ane . 
 
 
 
 
 

 
 
 
 
 
 Experimental support, please
 view the build logs 
 for errors. Generated by
 
 
 L
 A 
 T
 E 
 
 xml 
 
 .
 
 
 Instructions for reporting errors 
 We are continuing to improve HTML versions of papers, and your feedback helps enhance accessibility and mobile
 support. To report errors in the HTML that will help us improve conversion and rendering, choose any of the
 methods listed below: 
 
 Click the "Report Issue" ( 
 
 ) button, located in the page header. 
 
 Tip: You can select the relevant text first, to include it in your report. 
 Our team has already identified the following issues . We appreciate your time reviewing and reporting rendering errors we
 may not have found yet. Your efforts will help us improve the HTML versions for all readers, because disability
 should not be a barrier to accessing research. Thank you for your continued support in championing open access for
 all. 
 Have a free development cycle? Help support accessibility at arXiv! Our collaborators at LaTeXML maintain a list of packages that need conversion , and welcome developer contributions . 
 
 
 
 
 
 We gratefully acknowledge support from
 our major funders ,
 member institutions , ,
 and all contributors.
 
 
 About 
 · 
 Help 
 · 
 Contact 
 · 
 Subscribe 
 · 
 Copyright 
 · 
 Privacy 
 · 
 Accessibility 
 · 
 Operational Status (opens in new tab) 
 
 

 
 Major funding support from 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
 
