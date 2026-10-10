# RFC: MPS dialect in MLIR

**URL:** <https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102>\
**Category:** MLIR\
**Created:** [February 20, 2024, 12:44pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102 "2024-02-20T12:44:33Z")\
**Posts on this page:** 20\
**Page:** 1

<div class="post-metadata">

**Author:** ![saksenadhruv](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/saksenadhruv/32/422_2.png) [@saksenadhruv](https://discourse.llvm.org/u/saksenadhruv)\
**Post date:** [February 20, 2024, 12:44pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/1 "2024-02-20T12:44:33Z")

</div>

## Overview

## This RFC proposes the implementation of a new MPS target in MLIR

This dialect is providing the ability for the MLIR ecosystem to target Apple devices. We implemented a new serialization target that allows compute acceleration on Apple platforms, and delivers best performance to general compute workloads across macOS, iOS, tvOS, visionOS, using the MetalPerformanceShadersGraph framework.

The new MPS target implements the following features:

- Introduces a new MPS dialect in-tree;
- Represents high level abstractions for general compute operations;
- Fully versioned, backward/forward compatible dialect with minimumDeploymentTarget for each of the major Apple operating systems;
- Serialization entirely based on MLIR bytecode.

## Context

The MPS dialect represents a general purpose compute IR, leveraged within Apple in the MetalPerformanceShadersGraph (or MPSGraph) framework. The framework offers to declaratively assemble a general purpose computational graph, compile and optimize it on a given Apple device, execute it using native Objective-C and Swift APIs and deliver the best performance on each Apple platform.

Apple CoreML, Pytorch, Tensorflow, JAX, ONNX are frontends that today target MPSGraph on Apple devices in various capacities, either through Objective-C/Swift APIs, or within the MLIR dialect-to-dialect conversions.

## Motivations

The addition of the MPS dialect in MLIR allows projects building on top of MLIR to use the MPS dialect as an exchange format in order to target Apple platforms. The workflow would be to serialize a versioned MPS module providing a minimum deployment target for an OS version, using the standard MLIR bytecode infrastructure. Apple natively supports the MPS MLIR bytecode as input with its `mpsgraphtool` publicly available as part of macOS 14.0+, and then integrated as part of an Xcode project. The tool allows to convert the MPS MLIR bytecode into an mpsgraph package deployable on devices.

The community will also benefit from having the MPS dialect in-tree to leverage the large amount of bytecode tests we currently rely on internally to verify forward and backward compatibility of MLIR bytecode format. We did catch issues during our regular LLVM upgrades and having this test set in-tree would allow breaking changes to be easily caught and fixed. The MPS dialect would also be the first versioned dialect in-tree, and serve as a reference for anyone trying to implement a stable and versioning scheme using the primitives offered by MLIR.

One can even imagine a future direction where compute graphs in MPS dialect can be lowered to non-Apple HW too by converting them to other dialects, for example deploying on Nvidia or CPU or RISC-V with open source community developing open source conversions to provide cross-platform support.

## MPS Dialect description

The MPS dialect currently contains 222 operations and it is designed as a stable set of operations able to support the major higher level compute frameworks. As such, the IR generally expresses the most common operations from the major compute and ML frameworks. The general design combines three principles:

- Fidelity to MPSGraph Objective-C/Swift APIs;
- Apple Backend and OS agnostic;
- Limited the operation footprint. The amount of operations is expected to grow only if new functionality cannot be mapped to existing MPS dialect operations.

## Directory Setup

MPS header files will be in include/mlir/Target/MPS, include/mlir/Dialect/MPS. Sources files will be in lib/Target/MPS, lib/Dialect/MPS.

## MLIR Dependencies

The MPS dialect does not depend directly on any dialect upstream. Particularly, a serialization/deserialization functionality will be exposed such that users can leverage the IR to generate versioned MLIR bytecode files that could be read in a backward compatible fashion. No current MLIR dialect is dependent on MPS. The MPS dialect is intended to remain general enough to support any major compute framework, and at the same time, independent of any particular Apple target.

#### Who are the future contributors/maintainers beyond those who propose the dialect?

Compute Frameworks team at Apple would be the main contributors and maintainers of this dialect as it is used in the shipping MetalPerformanceShadersGraph framework since 2020.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 20, 2024, 1:44pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/2 "2024-02-20T13:44:37Z")

</div>

Thank you for the RFC.

Is there a public branch we can look at for how the dialect is composed? I primarily would like to see the granularity of ops, types and conventions employed in order to have a better mental map of how this fits with its peers.

Off hand, I am -1 on accepting this into the `mlir` sub-project itself. But I am potentially +1 (pending more detail on how this is put together) on creating a new top level `ml-dialects` project to house it (I know the name is not a perfect match to what this is but I’m trying to layer this in my head).

My opinion could be changed on the above with more discussion about how this fits within the tooling flows that currently exist. It isn’t clear to me for example whether this would be used as part of a compiler that is generating low level code for an Apple part (clang, mojo, iree, etc) at a similar layer of abstraction as, say, SPIR-V or llvm. Or whether this layers below ml and various user level frameworks as a way to identify large, device specific subgraphs early so that optimized kernels can be generated for them using vendor tools. A quick scan of the apple MPS docs suggests the latter to me.

In any case, I’ve got opinions on the proliferation of such vendor specific “macro ml op” libraries, but they are just that – opinions. I’d rather that they exist as maintained and accessible components than not. I just think that they stretch the MLIR subproject itself beyond its scope (and are logically a user of it, not a part of it).

Note: as has been discussed previously, there has been debate as to whether adding new dialects of this form are appropriate to only be advertised as an “MLIR” RFC. Especially if we are discussing it as a potential top level project, it needs to be raised community wide.

---

<div class="post-metadata">

**Author:** ![saksenadhruv](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/saksenadhruv/32/422_2.png) [@saksenadhruv](https://discourse.llvm.org/u/saksenadhruv)\
**Post date:** [February 21, 2024, 6:32am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/3 "2024-02-21T06:32:43Z")

</div>

Hi Stella,

Thank you for your thoughts, responses inline,

> [@stellaraccident](#):
>
> Is there a public branch we can look at for how the dialect is composed? I primarily would like to see the granularity of ops, types and conventions employed in order to have a better mental map of how this fits with its peers.

We don’t have a public branch exactly but I can send you our tablegen files or documentation, there is nothing stopping us from sharing this  
of course we will have a PR up once this RFC is green-lit for everyone to review fully.

[MPSOps.pdf](https://discourse.llvm.org/uploads/short-url/AlZchV8ILC4CTbCMrT4gn0OGcu4.pdf) (1.4 MB)

> [@stellaraccident](#):
>
> Or whether this layers below ml and various user level frameworks as a way to identify large, device specific subgraphs early so that optimized kernels can be generated for them using vendor tools. A quick scan of the apple MPS docs suggests the latter to me.

I would say the latter is correct, ML frameworks like JAX already are using this to layer underneath and pass subgraphs to be translated to MPS dialect and deployed for best performance on various Apple Silicon IPs.  
It is not GPU only, it brings the Neural Engine support as well to MLIR users.

So the tooling story would essentially be opening a wide door to various MLIR dialects to target Apple Silicon.

> [@stellaraccident](#):
>
> I’d rather that they exist as maintained and accessible components than not. I just think that they stretch the MLIR subproject itself beyond its scope (and are logically a user of it, not a part of it).

So as the RFC states as one of the benefits, the contribution here aims to add numerous extensive tests for bytecode format and also act as an example for other dialects to use to start moving towards forwards and backwards compatibility.

It extends the MLIR ecosystem also in the same way SPIRV brings Vulkan, or rocdl/amd\_gpu brings AMD HW or nvvm/nvgpu dialect brings Nvidia HW, and recently Intel proposing its own offering here we are opening the door for everyone to have a way to target Apple Silicon.

As long as users target this dialect they get a pretty optimized runtime and a history and commitment of high maintenance from Apple for these frameworks, which helps us begin to bring a support path for a platform with a billion users.

Given the numerous pros it brings to the table we humbly urge to reap the benefits of this contribution.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 7:42am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/4 "2024-02-21T07:42:09Z")

</div>

Thank you for the response. And also doubly thank you for being an early adopter of some of the features like bytecode and compatibility tooling. I have a good sense of the kind of investment involved in being early on that kind of train, and it is very much appreciated.

Thank you for sharing the PDF – it was quite helpful in getting a sense of what this is.

I’ve left some inline comments below that I expect will be taken somewhat negatively (although I’ve meant them as trying to share thoughts and experiences on how to get things done in this project), so I’d like to first make a couple of positive points and suggestions:

- I appreciate the level of investment and care that goes into something like this. While I personally prefer a different level of solution – I’ve seen enough of them to recognize the battle scars and lessons embedded in some of what I can see.
- I do think that it would be for the benefit of everyone if this were open sourced and available as a way for targeting Apple parts. Thank you for taking the steps to do so.
- The last 2-3 times I have been involved in discussions about expanding MLIR’s charter in these directions, consensus was not achieved. Those projects all continue to live quite healthy lives as OSS solutions outside of MLIR itself. And letting them continue to evolve in that way has let the community assess and form opinions over the kind of timeframe that the LLVM community likes to consider such changes of direction.
- There may be a place in LLVM proper for such a curated collection of ML dialects and integrations. I believe there is a roundtable at EuroLLVM that is re-opening some discussion around that and seeing if there is a consensus to be had on there being _a place_ for things in this general category. This would be a discussion for the wider community.

> [@saksenadhruv](#):
>
> of course we will have a PR up once this RFC is green-lit for everyone to review fully.

Just to set expectations, I have never once seen the LLVM community accept something sight unseen like this. Even if it were 100% aligned, the scope and level of variance this represents from what is in-tree most certainly qualifies as a [major change](https://llvm.org/docs/DeveloperPolicy.html#making-a-major-change). It’s going to be a discussion, and it is going to be taking the hard way through to try to come to a consensus on such a large body of code and ideas that no one can see.

Just my 2 cents after having tried the hard way once or twice…

> [@saksenadhruv](#):
>
> It extends the MLIR ecosystem also in the same way SPIRV brings Vulkan, or rocdl/amd\_gpu brings AMD HW or nvvm/nvgpu dialect brings Nvidia HW, and recently Intel proposing its own offering here we are opening the door for everyone to have a way to target Apple Silicon.

Not to nit-pick, but this is a very-very different level of abstraction and an apples/oranges comparison. The other cited dialects (including Intel’s recent RFC) are designed to facilitate code generation for low level targeting of vendor’s offerings, and they work in complementary ways in that fashion to enable compilers to be built with the low level facilities that have been developed in MLIR over many years, treating these devices as programmable at a detailed level. The level of abstraction here is actually closer to Torch, ONNX, TF, etc. If I had to draw a parallel, it would most likely be to CUDNN, in terms of level/approach – but with a tool flow more appropriate for deployment to clients.

Apple can of course choose to provide whatever level of programmability for its parts that it wishes, but this level of solution is quite a bit outside of the norm for what the MLIR project itself accepts. So far, the project has chosen to stay out of this area, and if opening that door, we really should be evaluating several other options (some of which also come with other features like a fully open, MLIR based compilation stack, not just an interface to a vendor’s proprietary toolchain).

I’m personally -1 on extending the MLIR project itself to take on such a scope that:

- Does not interoperate with any part of the code generation stack, like the other pieces do.
- Is based on a specific high level opset that is pegged to a single vendor’s proprietery compiler (i.e. if the community were to extend the MLIR charter in this way, I would strongly advocate that we take in something open that the community could truly own and adapt).
- Would add a very heavy “ML scale” opset as a dependency that we all have to pay for in terms of build time and complexity.
- Is not open for design feedback and evolution: reading the PDF (thank you for providing it), I can already see that there are a number of things that we would want to discuss/change as part of upstreaming, but it is unclear if that is the style of development that is envisioned.

That doesn’t mean that I’m opposed to this existing as an open-source project in general or as part of LLVM (as either a new top-level project, incubator, etc). Having been around the block a number of times, I imagine you have some legal/policy constraints that force you a bit into this big-reveal/non-incremental style of direct contribution. If that is the case, there may be other ways to bring this into the LLVM Foundation and let it evolve a bit more naturally without trying to get a summary judgment on whether the project should pivot in this way in one step. That kind of consensus is going to be very hard to achieve, I imagine.

> [@saksenadhruv](#):
>
> So the tooling story would essentially be opening a wide door to various MLIR dialects to target Apple Silicon.

But critically, none that are in-tree: very high level dialects can target this, but it would be a (large) raising from any dialect currently in MLIR.

---

<div class="post-metadata">

**Author:** ![mehdi\_amini](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/mehdi_amini/32/25595_2.png) [@mehdi\_amini](https://discourse.llvm.org/u/mehdi_amini)\
**Post date:** [February 21, 2024, 7:58am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/5 "2024-02-21T07:58:23Z")

</div>

Thanks for the proposal! It’s great to this coming after all your contributions to the MLIR bytecode infrastructure over the last year (and the nice talk at the last MLIR summit in the fall)!

I’m pretty excited to see this in tree to get an actual demonstrator of the bytecode stability and have a comprehensive test-suite. This is the first real production use-case to achieve this (and actually, most folks don’t know but a lot of the bytecode stability was built collaborative for supporting this dialect in the first place!).

If I understand correctly this is an egress dialect? What produces this dialect in the Apple ecosystem? You mentioned that Apple toolchain accepts natively this format as an input, but how are folks generating this dialect on your side right now?  
It would be interesting if you could elaborate on the possible paths of integration: who is the target audience (“MLIR users” is a heterogeneous group of people, operating at very different level of abstractions).

> [@stellaraccident](#):
>
> Off hand, I am -1 on accepting this into the `mlir` sub-project itself. But I am potentially +1 (pending more detail on how this is put together) on creating a new top level `ml-dialects` project to house it (I know the name is not a perfect match to what this is but I’m trying to layer this in my head).

Indeed it is an interesting direction, but one that involves the entire LLVM project.

In the meantime we can also bring back the work I started on [[RFC] Restructuring of the MLIR repo](https://discourse.llvm.org/t/rfc-restructuring-of-the-mlir-repo/4927) ; I only got blocked in my progress when I ended up not being sure about how to manage `mlir-opt` (as many `*-opt` tool as “shard” of the repo or a monolithic one, I’m a bit sad I got hung up on this…), to split up MLIR in a cleaner way.

That said: this seems all fairly orthogonal to this dialect: we shouldn’t block the inclusion of this dialect based on this. I see this as gatekeeping right now, and I have strong concern with such things here. MLIR needs to be able to continue to evolve and integrate “batteries”.  
I don’t have regrets on TOSA integration for example, this has proven quite low-maintenance on MLIR, and the maintainers have been pretty reactive to request for updating the dialect as we introduced changes in MLIR (for example when I had to update all dialect in-tree to start supporting `Properties`).  
I’m not too concerned by dialects that are thin and fairly isolated, we don’t build overly coupled “spaghetti plates” and keep these fairly easy to remove at any point.

My current grief is rather with the “spaghetti” we’re starting to see with all the interfaces that are inject dynamically everywhere: the project becomes fragile and impossible to grasp (The current monster is here: [llvm-project/mlir/include/mlir/InitAllDialects.h at a445474d3fdec2bdaaa42a6dc83c2fb01867076f · llvm/llvm-project · GitHub](https://github.com/llvm/llvm-project/blob/a445474d3fdec2bdaaa42a6dc83c2fb01867076f/mlir/include/mlir/InitAllDialects.h#L147-L177) ), I’m afraid we’re not picking at the real problem in-tree here!! Please focus the energy where it matters…

> [@stellaraccident](#):
>
> The other cited dialects (including Intel’s recent RFC) are designed to facilitate code generation for low level targeting of vendor’s offerings,

This is true to some extent, but on the other hand we’re also entering an era where the HW becomes more specialized, and targeting existing widely available accelerator requires a very different approach instead of just “low-level codegen” (not everything is suitable for a LLVM target?), these can also be seen a “virtual ISA” for modern accelerators (I had one in my pocket hey!)

> [@stellaraccident](#):
>
> So far, the project has chosen to stay out of this area,

Mmmmmm TOSA?

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 8:40am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/6 "2024-02-21T08:40:47Z")

</div>

> [@mehdi\_amini](#):
>
> This is true to some extent, but on the other hand we’re also entering an era where the HW becomes more specialized, and targeting existing widely available accelerator requires a very different approach instead of just “low-level codegen” (not everything is suitable for a LLVM target?), these can also be seen a “virtual ISA” for modern accelerators (I had one in my pocket hey!)

I don’t disagree on the general trend, but I don’t think we’ve seen enough to be laying down long term defacto policy yet. This is the input IR of Apple’s ML compiler. At the 10,000 ft level, it is not unlike quite a number of people’s input IR to their compilers. And that happens to be one and the same with how you are supposed to target their silicon (but that is a choice they have made). Just with my ML Framework Dev hat on, I am very skeptical about living in a world where we have critical infrastructure like this being driven by a single-vendor agenda and an opset of this shape, and I think that we should be more protective of the ability for the core infra to evolve than just accepting such things without more discussion and analysis. If that was the approach that was taken 20 years ago, we wouldn’t have LLVM.

That is not to say that we shouldn’t find a way to embrace the world we live in: this is why I wish there was an ML integration project of some kind to house these things (or that we had a sane approach to out of tree components).

> [@mehdi\_amini](#):
>
> That said: this seems all fairly orthogonal to this dialect: we shouldn’t block the inclusion of this dialect based on this. I see this as gatekeeping right now, and I have strong concern with such things here. MLIR needs to be able to continue to evolve and integrate “batteries”.

I’m going to disagree. I am not so eager to have “ML batteries” in MLIR-proper that I am willing to forgo the technical or organization discussions which are long-long overdue and unresolved. I don’t like the fragmentation either, and I have to live with it every day. But expanding the charter of MLIR like this is not something that I will be getting behind without some much more convincing arguments. I think we’re at the point of growth of this project that unless if we better organize it, we are doing a disservice by including more ad-hoc expansions of what it does. I want a real plan for growth before we stray into the ML frontend in tree. If we are having trouble dealing with the level of fragmentation we have, it will get 10x worse by ad-hoc moving up stack without a plan.

I’ll be at EuroLLVM. I think we have a roundtable to discuss some of this.

> [@mehdi\_amini](#):
>
> Mmmmmm TOSA?

I knew you were going to bring that up 🙂 Suffice to say that there were many things that were lumped into MLIR in the early days that I think would call for a different categorization now. Hindsight is 20-20 but I wish we’d held a better line on the dialects and project organization in those days. But there is often a bit of cambrian explosion when such projects start. We aren’t there anymore.

I know I argued in favor of some of these classes of things many years ago (I think I was the first one to send an email making an impassioned plea for “batteries”). And folks here were right to help me curb my enthusiasm for expanding the project in some of those directions too soon.

> [@mehdi\_amini](#):
>
> In the meantime we can also bring back the work I started on [[RFC] Restructuring of the MLIR repo](https://discourse.llvm.org/t/rfc-restructuring-of-the-mlir-repo/4927) ; I only got blocked in my progress when I ended up not being sure about how to manage `mlir-opt` (as many `*-opt` tool as “shard” of the repo or a monolithic one, I’m a bit sad I got hung up on this…), to split up MLIR in a cleaner way.

I think it would be good to bring the topic back up and have a fresh look at it. I’m not sure that now, a couple years on, that was an aggressive enough split.

---

<div class="post-metadata">

**Author:** ![mehdi\_amini](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/mehdi_amini/32/25595_2.png) [@mehdi\_amini](https://discourse.llvm.org/u/mehdi_amini)\
**Post date:** [February 21, 2024, 9:14am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/7 "2024-02-21T09:14:41Z")

</div>

> [@stellaraccident](#):
>
> I am very skeptical about living in a world where we have critical infrastructure like this being driven by a single-vendor agenda and an opset of this shape,

Nobody is standardize on this op-set right now: providing the ability for folks to interconnect has nothing to do with relinquishing any “critical infrastructure”: it’s not like we’re taking anything in the “standard dialect”.

> [@stellaraccident](#):
>
> protective of the ability for the core infra to evolve

I don’t understand what you refer to, can you elaborate please? What is “Core Infra” here? How would MPS prevent the evolution? (I explicitly addressed this in my previous comment I believe).

I also linked at example of the **real** issues that affect the project today (and have nothing to do with MPS): please chime in on finding solutions to “external interface” if you’re actually concerned with the health of the “core infra” and the robustness of MLIR. I don’t see issues to be with the “peripheral” dialects right now (ingress or egress) but with the spaghetti plate in the middle of it.

> [@stellaraccident](#):
>
> But expanding the charter of MLIR like this is not something that I will be getting behind without some much more convincing arguments.

You are claiming an expansion. I claim this is a mischaracterization. We never excluded this kind of things, otherwise TOSA wouldn’t be there. This is the expected and natural evolution of the project, the guidelines on “adding a dialect” were carefully debated and written for sustaining this.

> [@stellaraccident](#):
>
> I’ll be at EuroLLVM. I think we have a roundtable to discuss some of this.

I am not sure the roundtable has anything to do with this topic actually. It’s interesting we expect a different round-table since we both reviewed the proposal 🙂

> [@stellaraccident](#):
>
> > [@mehdi\_amini](#):
> >
> > Mmmmmm TOSA?
> 
> I knew you were going to bring that up 🙂 Suffice to say that there were many things that were lumped into MLIR in the early days that I think would call for a different categorization now. Hindsight is 20-20 but I wish we’d held a better line on the dialects and project organization in those days. But there is often a bit of cambrian explosion when such projects start. We aren’t there anymore.

You are rewriting the history in a funny way… You actually have it entirely backward here 🙂  
In the early days we were much more conservative. The first proposal was to add a ONNX dialect and we rejected it **because** it was too early to take such component.  
On the other hand TOSA arrived much much later at a point where we regretted not taking ONNX and the infra and the repo being much mature, we knew how to take this kind of component without coupling it to the entire repository.

> [@stellaraccident](#):
>
> I want a real plan for growth before we stray into the ML frontend in tree

This is an egress dialect, and you’re talking about frontend, I’m not sure I follow.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 10:15am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/8 "2024-02-21T10:15:14Z")

</div>

> [@mehdi\_amini](#):
>
> Nobody is standardize on this op-set right now: providing the ability for folks to interconnect has nothing to do with relinquishing any “critical infrastructure”: it’s not like we’re taking anything in the “standard dialect”.

But it does. The layers that get connected or bypassed are part of the normal discussion we have for every dialect – and we try to make sure things have some kind of coherent way they interconnect. We’re having that discussion right now on the Intel RFC with respect to how it relates to its peers. We’ve had it for every other dialect because if the layering matters and creates certain usage patterns.

This dialect has nothing in tree that can lower to it and it doesn’t lower to anything. It is a dialect not unlike many input dialects for specific compilers. Those are users of MLIR. It is a special pride of placement to elevate such a thing to be a part of MLIR. I don’t see the alignment here. And I happen to know that there are literally dozens of things just like this in our user’s codebases…

What is our policy towards those? We are not set up to handle the scale of this class of dialect (which I call an ml frontend dialect because it is just like any number of others I see and work with at that tier all the time). If we accept only one, it will become some form of defacto. If we accept them all, I don’t know how we would manage that with the current project structure.

> [@mehdi\_amini](#):
>
> I don’t understand what you refer to, can you elaborate please? What is “Core Infra” here? How would MPS prevent the evolution? (I explicitly addressed this in my previous comment I believe).

I have a thought bubble of this in my head, but I’m going to leave this for now. It’s too far afield. Was basically referring to the need to definite more of the core infra _for ml_.

> [@mehdi\_amini](#):
>
> if you’re actually concerned with the health of the “core infra” and the robustness of MLIR

I wish I understood that. If I’m going to have a core infra side project, it’ll probably end up being the dynamic linking situation, which seems to keep being brought up to me by various people weekly. And that has left me staring at the MLIR dependency and API situation, crying a bit, and wishing we had more focus and components in our project because I can’t quite see how to make anything sane out of what we have.

> [@mehdi\_amini](#):
>
> It’s interesting we expect a different round-table since we both reviewed the proposal 🙂

Having a coherent viewpoint on how the ml frontend stack layers and can be supported is part of what was the driver for that. This is implicated with that because this dialect can only be lowered to from very high level/framework level things. Just admitting one piece into MLIR doesn’t help. Just skimmed it again – this is squarely in the area of things that need to be worked out.

“In this work, we propose an upstream infrastructure plan, outlining which pieces of the MLIR infrastructure we should focus on, to build a common pipeline for diverse linear algebra input (ML, HPC), from various ingress IR (PyTorch, TensorFlow, ONNX, Fortran, C++), using a set of MLIR dialects (linalg, tensor, memref, vector, …) and interfaces into various dialects from downstream projects, tools and runtimes for further hardware-aware transformation and execution.”

> [@mehdi\_amini](#):
>
> You are rewriting the history in a funny way…

I think we’re both possibly remembering some different facets of a variety of discussions. There were quite a few other chapters of similar dialect inclusion discussions. I’m not sure TOSA would have been decided how it was at any point in the project other than when it was accepted. Earlier and, as your say, things still forming. Later and the pressure was already starting to exist of not taking sides in a messy debate on this class of dialects. It was in those subsequent debates that I recall arguing more for inclusion, but in the time since I’ve wished that we had broken the project up… Not just because it is getting unmanageable but because it would have better allowed some of these ancillary things to grow and evolve better on their own trajectory if they had been better clustered with things like them.

> [@mehdi\_amini](#):
>
> This is an egress dialect, and you’re talking about frontend, I’m not sure I follow.

In my world, this would squarely be an ml frontend dialect. This one happens to be the input for Apple’s compiler and exists at the same level of abstraction of a lot of others. I don’t know how else to say it. There are a lot of them and that’s what I call them.

---

<div class="post-metadata">

**Author:** ![mehdi\_amini](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/mehdi_amini/32/25595_2.png) [@mehdi\_amini](https://discourse.llvm.org/u/mehdi_amini)\
**Post date:** [February 21, 2024, 10:33am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/9 "2024-02-21T10:33:12Z")

</div>

> [@stellaraccident](#):
>
> But it does. The layers that get connected or bypassed are part of the normal discussion we have for every dialect – and we try to make sure things have some kind of coherent way they interconnect. We’re having that discussion right now on the Intel RFC with respect to how it relates to its peers. We’ve had it for every other dialect because if the layering matters and creates certain usage pattern

Sure… this is about ecosystem consistency to me.  
But I don’t see the connection to the quote I was answering. Specifically you wrote “have critical infrastructure like this”: what is “this”? What is “critical infrastructure” here? Where is the dependency?

> [@stellaraccident](#):
>
> I have a thought bubble of this in my head, but I’m going to leave this for now. It’s too far afield. Was basically referring to the need to definite more of the core infra _for ml_.

OK, so should I understand that all of your concerns about “core infra” and others you expressed in this thread aren’t about the MLIR project as it exists today?

> [@stellaraccident](#):
>
> build a common pipeline for diverse linear algebra input (ML, HPC), from various ingress IR (PyTorch, TensorFlow, ONNX, Fortran, C++), using a set of MLIR dialects (linalg, tensor, memref, vector, …)

MPS is proposed as an egress here as far as I can tell, this likely explains the disconnect: you’re quoting purely an ingress → “codegen dialects” flow as far as I can tell.

---

<div class="post-metadata">

**Author:** ![rengolin](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/rengolin/32/327_2.png) [@rengolin](https://discourse.llvm.org/u/rengolin)\
**Post date:** [February 21, 2024, 10:43am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/10 "2024-02-21T10:43:05Z")

</div>

First, I agree with almost everything @stellaraccident said above. I put some “hearts” on her responses but this does not convey my level of agreement.

> [@stellaraccident](#):
>
> In any case, I’ve got opinions on the proliferation of such vendor specific “macro ml op” libraries, but they are just that – opinions. I’d rather that they exist as maintained and accessible components than not. I just think that they stretch the MLIR subproject itself beyond its scope (and are logically a user of it, not a part of it).

This is really important. It’s ok to have a lot of ingress dialects (one per framework or more), but those dialects belong to their respective projects. That’s why we have `torch-mlir` as a separate project. It’s ok to have multiple hardware optimization dialects, if they lower to the common egress dialects (SIRV and LLVM). But it’s not ok to have multiple egress dialects that don’t go anywhere.

Your case is the former above. We already have StableHLO, Torch in other projects, we already have TOSA upstream, and those all lower to Linalg & friends. If you need such a high level dialect to lower to your hardware, it hints that you’re not using most of the existing infrastructure. If that’s true, then this would fragment the MLIR ecosystem a lot and I’d be a strong -1.

A common ML abstraction (be it TOSA, TCP or ml\_program) is definitely a way to use it and should be considered. At Intel, we’re working hard to integrate our pipelines to the existing infrastructure and we’re changing that infrastructure upstream to make it work better for everyone.

> [@mehdi\_amini](#):
>
> That said: this seems all fairly orthogonal to this dialect: we shouldn’t block the inclusion of this dialect based on this. I see this as gatekeeping right now, and I have strong concern with such things here. MLIR needs to be able to continue to evolve and integrate “batteries”.

I don’t understand this argument. We’re discussing very high level design decisions that could impact the project as a whole and you’re labeling this “gatekeeping”?

> [@mehdi\_amini](#):
>
> and targeting existing widely available accelerator requires a very different approach instead of just “low-level codegen” (not everything is suitable for a LLVM target?), these can also be seen a “virtual ISA” for modern accelerators

As a data point, this is what Intel Labs [proposed](https://arxiv.org/abs/2104.05755) some time ago, and when we tried to [include](https://github.com/plaidml/tpp-mlir) that into MLIR we created our own dialect, but soon realised (when sharing with the community) that we could just change the `tensor` and `linalg` dialects to match our semantics.

I’d expect the Apple effort to do the same, as I expect anyone else.

> [@stellaraccident](#):
>
> I am not so eager to have “ML batteries” in MLIR-proper that I am willing to forgo the technical or organization discussions which are long-long overdue and unresolved. I don’t like the fragmentation either, and I have to live with it every day.

Hear, hear.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 10:47am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/11 "2024-02-21T10:47:46Z")

</div>

> [@mehdi\_amini](#):
>
> MPS is proposed as an egress here as far as I can tell, this likely explains the disconnect: you’re quoting purely an ingress → “codegen dialects” flow as far as I can tell.

No I’m not. It’s an egress from what? From literally nothing we have. So a standalone dialect that is looking for a project to land in.

Most of the people with this class of thing are users of MLIR and just… Have a project for it. We haven’t historically accepted loose leaf dialects like that (in fact the debates have resolved vigorously against) and if we started to… There are a lot of them.

(And just to reiterate, I’m all for finding a way for the LLVM foundation to help open source this dialect. But I’m arguing against that being in the MLIR project itself)

---

<div class="post-metadata">

**Author:** ![mehdi\_amini](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/mehdi_amini/32/25595_2.png) [@mehdi\_amini](https://discourse.llvm.org/u/mehdi_amini)\
**Post date:** [February 21, 2024, 11:16am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/12 "2024-02-21T11:16:42Z")

</div>

> [@stellaraccident](#):
>
> > [@mehdi\_amini](#):
> >
> > you’re quoting purely an ingress → “codegen dialects” flow as far as I can tell.
> 
> No I’m not.

The quote has literally the word “ingress”: " diverse linear algebra input (ML, HPC), from **various ingress IR** (PyTorch, TensorFlow, ONNX, Fortran, C++), using a set of MLIR dialects (linalg, tensor, memref, vector, …)"

> [@stellaraccident](#):
>
> We haven’t historically accepted loose leaf dialects like that (in fact the debates have resolved vigorously against)

Please provide references! Other than ONNX and TOSA, I can’t connect right now. And the most recent leaf (TOSA) is in-tree as a proof of contradiction to your claim right now.

> [@rengolin](#):
>
> I don’t understand this argument. We’re discussing very high level design decisions that could impact the project as a whole and you’re labeling this “gatekeeping”?

No we’re not: this is a dialect proposal, for which we have guidelines: [Developer Guide - MLIR](https://mlir.llvm.org/getting_started/DeveloperGuide/#guidelines-on-contributing-a-new-dialect-or-important-components) ; these includes for example the positioning dialect (egress for example, benefit to the community, etc.)  
Trying to shove a “project level” re-organization with top-level ml components in the discussion, or making it a blocker to be able to discuss a single dialect is an easy gatekeeping strategy IMO, and I see this as a toxic approach to the MLIR project evolution.  
There is nothing that justifies this coupling of discussion when there is no actual coupling. Even after years in the repo, TOSA can be trivially removed: it has incurred no complexity on the codebase and isn’t highly coupled to the project. This is the nature of peripheral dialects: it’s much different than tensor/linalg/affine/vector/index/bufferization/… which are intertwined in subtle and hard to grasp ways.

> [@rengolin](#):
>
> If that’s true, then this would fragment the MLIR ecosystem a lot and I’d be a strong -1.

That’s like saying there is “one true answer” to DSL compilers: either you go to LLVM or you don’t belong here. I strongly object to this view: “traditional LLVM codegen” is one possible egress, MLIR isn’t build just around this one funnel idea. It would be similarly a dangerous slope to start claiming that “linalg is the one true answer for linear algebra code generation and any other approach is fragmenting the ecosystem”.  
The counter point to this is that everyone should be very defensive on any new things happening in the repo, because it immediately becomes a “land grabbing” that can then be claimed later to object a new path under the pretense of “fragmenting the ecosystem”.  
And don’t get me wrong: I believe in consistency and “fragmentation” is something important to look for, but it has to be done with respect to equivalence class (for example when folks wanted to emit C without using emitC: we heavily discussed whether the pros/cons and how different the approach were and whether they justified 2 infra for the same thing, similarly I’m concerned about the “Intel GPU codegen building a SPIRV codegen path that is redundant with the SPIRV dialect”).

> [@rengolin](#):
>
> As a data point, this is what Intel Labs [proposed](https://arxiv.org/abs/2104.05755) some time ago, and when we tried to [include](https://github.com/plaidml/tpp-mlir) that into MLIR we created our own dialect, but soon realised (when sharing with the community) that we could just change the `tensor` and `linalg` dialects to match our semantics.
> 
> I’d expect the Apple effort to do the same, as I expect anyone else.

You probably missed all the work on the bytecode, otherwise you’d realized that these are entirely different categories of target/product/integration and that we really don’t want to take on the stability/versioning requirement that comes with a “virtual ISA” inside of “tensor” or “linalg”.  
But also, again, you worked on a CPU/GPU, I’ve seen HW accelerators that have a vastly different model that does not fit the LLVM target: for example the HW itself may want to perform a full-tensor “convolution” by setting up some register describing the memory layout of the input tensor.

---

<div class="post-metadata">

**Author:** ![rengolin](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/rengolin/32/327_2.png) [@rengolin](https://discourse.llvm.org/u/rengolin)\
**Post date:** [February 21, 2024, 11:41am UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/13 "2024-02-21T11:41:41Z")

</div>

> [@mehdi\_amini](#):
>
> Trying to shove a “project level” re-organization with top-level ml components in the discussion, or making it a blocker to be able to discuss a single dialect is an easy gatekeeping strategy IMO, and I see this as a toxic approach to the MLIR project evolution.

I am not comfortable with this description of my behaviour. I’d like you to please stop characterizing arguments as pro or against, pusher or blocker.

Indeed, such a behaviour would be toxic, but so far the only toxic thing I’ve seen in this discussions have been your simplification and aggressive rebutes of arguments from people you don’t seem to agree with.

My interpretation of Stella’s responses is that she had no negative feeling towards this particular proposal, but could see a trend going in a direction that would exacerbate our current problems and she was trying to point out.

I supported her arguments, in my interpretation, because I see similar problems and would like to find a better way to solve them. If I had sensed “gatekeeping” on her behaviour, I would not have supported her, even if I did agree with the arguments.

My example with TPP wasn’t to compare dialects, just behaviour: We had a grand idea, we created a new dialect with full lowering, we discussed with the community, there was great feedback, the decision was to rewrite our entire compiler to use pure linalg instead, which we did at a great cost, but it worked and we were quite happy with the end result.

I believe this was also better for the MLIR community in general and this is why I’m advocating for others to do the same. Personal experiences, personal journey, personal opinion, given without judgement for the betterment of the whole community. Simple as that.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 4:49pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/14 "2024-02-21T16:49:12Z")

</div>

> [@mehdi\_amini](#):
>
> No we’re not: this is a dialect proposal, for which we have guidelines: [Developer Guide - MLIR](https://mlir.llvm.org/getting_started/DeveloperGuide/#guidelines-on-contributing-a-new-dialect-or-important-components)

We are. Do we need to have this discussion again? The last time this argument was made _about this topic_ there were strong opinions that that policy did not apply to make changes of scope, and that we needed to follow the LLVM dev policy.

We are discussing here bringing in a new kind of thing that is one of a broad category of things that we have historically debated and not come to consensus to bring into MLIR itself.

And both the person who is primary for the development of the things that LLVM already has at this layer of abstraction and the person who has been working for over a year at normalizing some of these same intersecting issues are saying that this is not just a dialect change. Maybe we are thinking wrong about it, but that is a topic for discussion, not a policy loophole. And it needs to happen in a broader context and with more care than that policy was written to provide.

@clattner

---

<div class="post-metadata">

**Author:** ![saksenadhruv](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/saksenadhruv/32/422_2.png) [@saksenadhruv](https://discourse.llvm.org/u/saksenadhruv)\
**Post date:** [February 21, 2024, 6:54pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/15 "2024-02-21T18:54:17Z")

</div>

> [@mehdi\_amini](#):
>
> If I understand correctly this is an egress dialect?

That is correct. Any compiler or framework can convert to MLIR if you will and target Apple Silicon IPs. You wouldn’t specifically expect it to go through progressive lowering to do codegen for the Neural Engine for example. And some stuff can be sensitive, so we would have `MetalPerformanceShadersGraph.framework` accept this bytecode, massage it if needed and pass MLIR to the neural engine compiler to further produce a binary equivalent for it.

> [@mehdi\_amini](#):
>
> What produces this dialect in the Apple ecosystem? You mentioned that Apple toolchain accepts natively this format as an input, but how are folks generating this dialect on your side right now?

There are multiple ways to emit MLIR, one is to use our objC and Swift APIs of MPSGraph framework and construct it piece by piece.

Second you can use `mpsgraphtool` which we are shipping with latest macOS to convert your coreMLPackage or ONNX to the mpsgraphpackage (which is MLIR bytecode).

Third JAX MPS backend is converting MLIR to MLIR, emitting it out and passing it to MPSGraph framework to execute on Apple platforms.

Below link shows some of the above functionality.

> **[Optimize machine learning for Metal apps - WWDC23 - Videos - Apple Developer](https://developer.apple.com/videos/play/wwdc2023/10050/?time=970)**
>
> Discover the latest enhancements to accelerated ML training in Metal. Find out about updates to PyTorch and TensorFlow, and learn about...

> [@mehdi\_amini](#):
>
> It would be interesting if you could elaborate on the possible paths of integration: who is the target audience (“MLIR users” is a heterogeneous group of people, operating at very different level of abstractions).

Once it goes open source, people don’t have to go through blackbox converter tools and a lot of these tools can also be publicized. We can have people emit MPS dialect and use MPSGraph as a “driver” if you will to execute that code (like codegen a call to MPSGraph even) and get best performance on Apple platform for any hard hitting compute graph.

To you your point specific “people” / “users” can (if they choose to) for example be ONNXRuntime, Executorch, JAX, TFLite, even TOSA.

> [@stellaraccident](#):
>
> Not to nit-pick, but this is a very-very different level of abstraction and an apples/oranges comparison. The other cited dialects (including Intel’s recent RFC) are designed to facilitate code generation for low level targeting of vendor’s offerings, and they work in complementary ways in that fashion to enable…

Yes they are different levels, but just like you can’t target hardware specific features of different HW without the vendor specific dialect to target (eg. Nvidia tensor cores, AMD instructions, etc.), there is no way to target the Neural Engine or Apple Silicon GPU HW features without having a dialect to target from other dialects in MLIR to lower to.

> [@stellaraccident](#):
>
> That doesn’t mean that I’m opposed to this existing as an open-source project in general or as part of LLVM (as either a new top-level project, incubator, etc).

I appreciate that fully, few points though, in general we are contributing a set of tests here to test bytecode for example. When we have an agreed on separate project to move this to, MPS dialect will be very easy to move out to that repo if the community agrees to that.

And at that point I expect other vendor specific dialects like TOSA, rocdl, nvvm, etc would also move out to that repo. There would be an agreed upon testing infrastructure where every LLVM PR would ensure those all dialects build and pass testing.

We don’t have to put this behind that effort which it seems could take quite a while, these are not mutually exclusive or even dependent. (Probably helps make your future case for it stronger 😉 )

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 7:15pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/16 "2024-02-21T19:15:48Z")

</div>

> [@saksenadhruv](#):
>
> Once it goes open source, people don’t have to go through blackbox converter tools and a lot of these tools can also be publicized. We can have people emit MPS dialect and use MPSGraph as a “driver” if you will to execute that code and get best performance on Apple platform for any hard hitting compute graph.

One nit and then I’m going to leave this thread to settle: landing in MLIR should not be conflated with it going open source or having the technology be accessible to developers. Those are completely separable activities, and in fact, my experience is that most people do separate them. It is completely within Apple’s control today to eliminate the blackbox converter tools regardless of acceptance in a specific directory within LLVM. If we want to land it in MLIR, we need to have the discussion of how it fits (or in this case is orthogonal) with the other pieces.

We’ve had this kind of discussion many times in the past and across a lot of companies and situations: the overall project is conservative and deliberative when it comes to abstraction levels… on purpose and because approaching the development in that way has had positive outcomes over the timeframes that the project considers. I know how much of a grind that can be and feel like (and have been frustrated by it many times), which is why I’ve been trying to suggest more accessible ways to approach it that don’t involve a first step of expanding the charter of a project and conversation that has years of history on it.

It is going to be a high bar to start single-party development from a closed source, fully formed dialect at this abstraction level within MLIR, and it won’t just be me saying that.

---

<div class="post-metadata">

**Author:** ![clattner](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/clattner/32/187_2.png) [@clattner](https://discourse.llvm.org/u/clattner)\
**Post date:** [February 21, 2024, 8:57pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/17 "2024-02-21T20:57:15Z")

</div>

This seems like a super cool development, but I agree with Stella’s macro point here: we can’t really discuss things “sight unseen”.

I have a mac and iphone - is there a way to test this end to end on something concrete (e.g. through the MLX stuff generating MLIR)? If not, it will be hard to justify the llvm project taking on maintenance for this. If so, then this sounds like an incredibly cool development.

-<User>

---

<div class="post-metadata">

**Author:** ![saksenadhruv](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/saksenadhruv/32/422_2.png) [@saksenadhruv](https://discourse.llvm.org/u/saksenadhruv)\
**Post date:** [February 21, 2024, 9:34pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/18 "2024-02-21T21:34:58Z")

</div>

> [@clattner](#):
>
> This seems like a super cool development, but I agree with Stella’s macro point here: we can’t really discuss things “sight unseen”.

Thank you, point totally taken, we are going to provide a working end to end example, this is our first step into open source for this to get feedback.

The separation of the dialect definition has already happened, we will discuss how to provide a more concrete “here is the code we want to upstream” ASAP.

> [@clattner](#):
>
> I have a mac and iphone - is there a way to test this end to end on something concrete (e.g. through the MLX stuff generating MLIR)?

Yes, we can provide examples to facilitate this as stated above, but when you use JAX or PyTorch or TF this already happens under the hood, I expect you mean to see some mlir source code and calls being used and code examples of it working.

> [@stellaraccident](#):
>
> One nit and then I’m going to leave this thread to settle: landing in MLIR should not be conflated with it going open source or having the technology be accessible to developers.

Absolutely, I was answering Mehdi’s question, in-tree or out of tree once we open source it will be no longer a blackbox, being in-tree has many benefits beyond just targeting the dialect as stated before.

---

<div class="post-metadata">

**Author:** ![stellaraccident](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/stellaraccident/32/177_2.png) [@stellaraccident](https://discourse.llvm.org/u/stellaraccident)\
**Post date:** [February 21, 2024, 9:44pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/19 "2024-02-21T21:44:15Z")

</div>

Thanks. Would love to have a look at the flow and tooling.

One of the things that is hard to evaluate from an abstract description is the impact to project infra – and not just the minimum that can be done by having dialect lit tests, etc but the cost of actually getting good coverage so we can know it is a quality piece of software.

Will have to have a look, but that alone may justify it being more of its own project (in tree, out of tree, whatever) vs embedded in a sub project: I’ve found that when these projects are not housed properly, there is too much friction in getting the tooling and testing in place, either resulting in it not happening to the extent it should, being done in a disconnected downstream, or always fighting with the containing project to keep overheads (both tooling/deps and automation) manageable. Would like to not keep piling technical debt on that axis for something like this.

---

<div class="post-metadata">

**Author:** ![anemet](https://sea1.discourse-cdn.com/flex021/user_avatar/discourse.llvm.org/anemet/32/16843_2.png) [@anemet](https://discourse.llvm.org/u/anemet)\
**Post date:** [March 11, 2024, 5:49pm UTC](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102/20 "2024-03-11T17:49:10Z")

</div>

> [@mehdi\_amini](#):
>
> > [@stellaraccident](#):
> >
> > The other cited dialects (including Intel’s recent RFC) are designed to facilitate code generation for low level targeting of vendor’s offerings,
> 
> This is true to some extent, but on the other hand we’re also entering an era where the HW becomes more specialized, and targeting existing widely available accelerator requires a very different approach instead of just “low-level codegen” (not everything is suitable for a LLVM target?), these can also be seen a “virtual ISA” for modern accelerators (I had one in my pocket hey!)

I want to add one more perspective from Apple on this one. While I completely agree with Mehdi that MPS is best considered as a high-level virtual ISA, we do lower to LLVM for some of the targets (e.g. the CPU) and we are hoping to contribute these pieces to MLIR as well. These paths progressively lower to Tosa, Tensor and other in-tree dialects.

> [@stellaraccident](#):
>
> No I’m not. It’s an egress from what? From literally nothing we have. So a standalone dialect that is looking for a project to land in.

Hopefully what I wrote above addresses this concern that somehow the MPS dialect would be standalone in-tree not interacting with the rest of the components. We are planning to contribute and maintain the code that interacts with MPS if the dialect is accepted.

[Next page](https://discourse.llvm.org/t/rfc-mps-dialect-in-mlir/77102.md?page=2)
