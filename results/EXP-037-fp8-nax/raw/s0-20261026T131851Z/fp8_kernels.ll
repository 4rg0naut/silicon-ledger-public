; ModuleID = '/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/harness/../raw/s0-20261026T131851Z/fp8_kernels.metal'
source_filename = "/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/harness/../raw/s0-20261026T131851Z/fp8_kernels.metal"
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v29-apple-macosx27.0.0"

%"struct.mpp::tensor_ops::matmul2d_descriptor" = type { i32, i32, i32, i8, i8, i8, i32 }
%"struct.metal::array" = type { [2 x i32] }
%struct._tensor_t = type opaque

@_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE = linkonce_odr local_unnamed_addr constant %"struct.mpp::tensor_ops::matmul2d_descriptor" { i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0 }

; Function Attrs: convergent nounwind
define void @mm_f8(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* noundef "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %9 = alloca %"struct.metal::array", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = alloca %"struct.metal::array", align 4
  %19 = alloca %"struct.metal::array", align 4
  %20 = alloca %"struct.metal::array", align 4
  %21 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %22 = alloca i8, i64 %21, align 8
  %23 = alloca i8, i64 %21, align 8
  %24 = tail call i64 @_ZN5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %25 = alloca i8, i64 %24, align 8
  %26 = alloca i8, i64 %21, align 8
  %27 = alloca i8, i64 %21, align 8
  %28 = alloca i8, i64 %24, align 8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %29 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !32, !noalias !35
  %30 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !41, !noalias !42
  %31 = bitcast i8* %22 to %struct._tensor_t*
  %32 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %32) #8
  %33 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 %29, i32* %33, align 4, !tbaa !28
  %34 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %30, i32* %34, align 4, !tbaa !28
  %35 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %35) #8
  %36 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 1, i32* %36, align 4, !tbaa !28
  %37 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %29, i32* %37, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %31, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %32, i8* nocapture nonnull readonly %35, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %35) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %32) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %23)
  %38 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !43, !noalias !44
  %39 = bitcast i8* %23 to %struct._tensor_t*
  %40 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %40) #8
  %41 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 %38, i32* %41, align 4, !tbaa !28
  %42 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %29, i32* %42, align 4, !tbaa !28
  %43 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %43) #8
  %44 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 1, i32* %44, align 4, !tbaa !28
  %45 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %38, i32* %45, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %39, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %40, i8* nocapture nonnull readonly %43, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %43) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %40) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %25)
  %46 = bitcast i8* %25 to %struct._tensor_t*
  %47 = bitcast float addrspace(1)* %2 to i8 addrspace(1)*
  %48 = bitcast %"struct.metal::array"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %48) #8
  %49 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 0
  store i32 %38, i32* %49, align 4, !tbaa !28
  %50 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 1
  store i32 %30, i32* %50, align 4, !tbaa !28
  %51 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %51) #8
  %52 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 1, i32* %52, align 4, !tbaa !28
  %53 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %38, i32* %53, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %46, i16 2, i8 addrspace(1)* readnone %47, i8* nocapture nonnull readonly %48, i8* nocapture nonnull readonly %51, i8 0, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %51) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %48) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %26)
  %54 = extractelement <2 x i32> %6, i64 1
  %55 = shl i32 %54, 6
  %56 = bitcast %"struct.metal::array"* %20 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %56) #8, !noalias !45
  %57 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 0
  store i32 0, i32* %57, align 4, !tbaa !28, !noalias !45
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 1
  store i32 %55, i32* %58, align 4, !tbaa !28, !noalias !45
  %59 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %59) #8
  %60 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %31, i16 2, i16 0, i16 0) #9
  %61 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %31, i16 2, i16 1, i16 0) #9
  %62 = sub i32 %61, %55
  %63 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %60, i32* %63, align 4
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 %62, i32* %64, align 4
  %65 = bitcast i8* %26 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %65, %struct._tensor_t* nocapture nonnull readonly %31, i16 2, i8* nocapture nonnull readonly %56, i8* nocapture nonnull readonly %59) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %59) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %56) #8, !noalias !45
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %27)
  %66 = extractelement <2 x i32> %6, i64 0
  %67 = shl i32 %66, 5
  %68 = bitcast %"struct.metal::array"* %19 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %68) #8, !noalias !48
  %69 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 0
  store i32 %67, i32* %69, align 4, !tbaa !28, !noalias !48
  %70 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 1
  store i32 0, i32* %70, align 4, !tbaa !28, !noalias !48
  %71 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %71) #8
  %72 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %39, i16 2, i16 0, i16 0) #9
  %73 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %39, i16 2, i16 1, i16 0) #9
  %74 = sub i32 %72, %67
  %75 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 %74, i32* %75, align 4
  %76 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %73, i32* %76, align 4
  %77 = bitcast i8* %27 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %77, %struct._tensor_t* nocapture nonnull readonly %39, i16 2, i8* nocapture nonnull readonly %68, i8* nocapture nonnull readonly %71) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %71) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %68) #8, !noalias !48
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %28)
  %78 = bitcast %"struct.metal::array"* %18 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %78) #8, !noalias !51
  %79 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 0
  store i32 %67, i32* %79, align 4, !tbaa !28, !noalias !51
  %80 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 1
  store i32 %55, i32* %80, align 4, !tbaa !28, !noalias !51
  %81 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %81) #8
  %82 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %46, i16 2, i16 0, i16 0) #9
  %83 = sub i32 %82, %67
  %84 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %46, i16 2, i16 1, i16 0) #9
  %85 = sub i32 %84, %55
  %86 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %83, i32* %86, align 4
  %87 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %85, i32* %87, align 4
  %88 = bitcast i8* %28 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %88, %struct._tensor_t* nocapture nonnull readonly %46, i16 2, i8* nocapture nonnull readonly %78, i8* nocapture nonnull readonly %81) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %81) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %78) #8, !noalias !51
  %89 = tail call i32 @air.get_simdgroup_size.i32() #10
  %90 = shl i32 %89, 2
  %91 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %8 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %91) #8
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %91, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #8, !tbaa.struct !54
  call void @__tensorops_impl_matmul2d_op_run_dv_fp8e4m3_dv_fp8e4m3_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %8, i8* noundef nonnull %26, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %27, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %28, i32 noundef 2, i32 noundef -1, i32 noundef -1, i32 noundef %90) #11
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %91) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %28) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %27) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %26) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %25) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %23) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #8
  ret void
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() #12
  %2 = trunc i64 %1 to i16
  %3 = tail call i16 @air.get_descriptor_size_tensor(i16 %2, i16 4) #10
  %4 = zext i16 %3 to i64
  ret i64 %4
}

; Function Attrs: mustprogress nounwind
define linkonce_odr i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() local_unnamed_addr #2 align 2 {
  ret i64 2
}

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare i16 @air.get_descriptor_size_tensor(i16, i16) local_unnamed_addr #3

; Function Attrs: argmemonly mustprogress nocallback nofree nosync nounwind willreturn
declare void @llvm.lifetime.start.p0i8(i64 immarg, i8* nocapture) #4

; Function Attrs: argmemonly mustprogress nocallback nofree nosync nounwind willreturn
declare void @llvm.lifetime.end.p0i8(i64 immarg, i8* nocapture) #4

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() #12
  %2 = trunc i64 %1 to i16
  %3 = tail call i16 @air.get_descriptor_size_tensor(i16 %2, i16 4) #10
  %4 = zext i16 %3 to i64
  ret i64 %4
}

; Function Attrs: convergent nounwind
define void @mm_mix8(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* noundef "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %9 = alloca %"struct.metal::array", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = alloca %"struct.metal::array", align 4
  %19 = alloca %"struct.metal::array", align 4
  %20 = alloca %"struct.metal::array", align 4
  %21 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %22 = alloca i8, i64 %21, align 8
  %23 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %24 = alloca i8, i64 %23, align 8
  %25 = tail call i64 @_ZN5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %26 = alloca i8, i64 %25, align 8
  %27 = alloca i8, i64 %21, align 8
  %28 = alloca i8, i64 %23, align 8
  %29 = alloca i8, i64 %25, align 8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %30 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !59, !noalias !62
  %31 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !68, !noalias !69
  %32 = bitcast i8* %22 to %struct._tensor_t*
  %33 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %33) #8
  %34 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 %30, i32* %34, align 4, !tbaa !28
  %35 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %31, i32* %35, align 4, !tbaa !28
  %36 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %36) #8
  %37 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 1, i32* %37, align 4, !tbaa !28
  %38 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %30, i32* %38, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %32, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %33, i8* nocapture nonnull readonly %36, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %36) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %33) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %24)
  %39 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !70, !noalias !71
  %40 = bitcast i8* %24 to %struct._tensor_t*
  %41 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %41) #8
  %42 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 %39, i32* %42, align 4, !tbaa !28
  %43 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %30, i32* %43, align 4, !tbaa !28
  %44 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %44) #8
  %45 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 1, i32* %45, align 4, !tbaa !28
  %46 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %39, i32* %46, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %40, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %41, i8* nocapture nonnull readonly %44, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %44) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %41) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %26)
  %47 = bitcast i8* %26 to %struct._tensor_t*
  %48 = bitcast float addrspace(1)* %2 to i8 addrspace(1)*
  %49 = bitcast %"struct.metal::array"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %49) #8
  %50 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 0
  store i32 %39, i32* %50, align 4, !tbaa !28
  %51 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 1
  store i32 %31, i32* %51, align 4, !tbaa !28
  %52 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %52) #8
  %53 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 1, i32* %53, align 4, !tbaa !28
  %54 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %39, i32* %54, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %47, i16 2, i8 addrspace(1)* readnone %48, i8* nocapture nonnull readonly %49, i8* nocapture nonnull readonly %52, i8 0, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %52) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %49) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %27)
  %55 = extractelement <2 x i32> %6, i64 1
  %56 = shl i32 %55, 6
  %57 = bitcast %"struct.metal::array"* %18 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %57) #8, !noalias !72
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 0
  store i32 0, i32* %58, align 4, !tbaa !28, !noalias !72
  %59 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 1
  store i32 %56, i32* %59, align 4, !tbaa !28, !noalias !72
  %60 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %60) #8
  %61 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %32, i16 2, i16 0, i16 0) #9
  %62 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %32, i16 2, i16 1, i16 0) #9
  %63 = sub i32 %62, %56
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %61, i32* %64, align 4
  %65 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %63, i32* %65, align 4
  %66 = bitcast i8* %27 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %66, %struct._tensor_t* nocapture nonnull readonly %32, i16 2, i8* nocapture nonnull readonly %57, i8* nocapture nonnull readonly %60) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %60) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %57) #8, !noalias !72
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %28)
  %67 = extractelement <2 x i32> %6, i64 0
  %68 = shl i32 %67, 5
  %69 = bitcast %"struct.metal::array"* %20 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %69) #8, !noalias !75
  %70 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 0
  store i32 %68, i32* %70, align 4, !tbaa !28, !noalias !75
  %71 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 1
  store i32 0, i32* %71, align 4, !tbaa !28, !noalias !75
  %72 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %72) #8
  %73 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %40, i16 2, i16 0, i16 0) #9
  %74 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %40, i16 2, i16 1, i16 0) #9
  %75 = sub i32 %73, %68
  %76 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 %75, i32* %76, align 4
  %77 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %74, i32* %77, align 4
  %78 = bitcast i8* %28 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %78, %struct._tensor_t* nocapture nonnull readonly %40, i16 2, i8* nocapture nonnull readonly %69, i8* nocapture nonnull readonly %72) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %72) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %69) #8, !noalias !75
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %29)
  %79 = bitcast %"struct.metal::array"* %19 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %79) #8, !noalias !78
  %80 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 0
  store i32 %68, i32* %80, align 4, !tbaa !28, !noalias !78
  %81 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 1
  store i32 %56, i32* %81, align 4, !tbaa !28, !noalias !78
  %82 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %82) #8
  %83 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %47, i16 2, i16 0, i16 0) #9
  %84 = sub i32 %83, %68
  %85 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %47, i16 2, i16 1, i16 0) #9
  %86 = sub i32 %85, %56
  %87 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %84, i32* %87, align 4
  %88 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 %86, i32* %88, align 4
  %89 = bitcast i8* %29 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %89, %struct._tensor_t* nocapture nonnull readonly %47, i16 2, i8* nocapture nonnull readonly %79, i8* nocapture nonnull readonly %82) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %82) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %79) #8, !noalias !78
  %90 = tail call i32 @air.get_simdgroup_size.i32() #10
  %91 = shl i32 %90, 2
  %92 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %8 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %92) #8
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %92, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #8, !tbaa.struct !54
  call void @__tensorops_impl_matmul2d_op_run_dv_f16_dv_fp8e4m3_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %8, i8* noundef nonnull %27, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %28, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %29, i32 noundef 2, i32 noundef -1, i32 noundef -1, i32 noundef %91) #11
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %92) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %29) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %28) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %27) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %26) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %24) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #8
  ret void
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() #12
  %2 = trunc i64 %1 to i16
  %3 = tail call i16 @air.get_descriptor_size_tensor(i16 %2, i16 4) #10
  %4 = zext i16 %3 to i64
  ret i64 %4
}

; Function Attrs: convergent nounwind
define void @mm_f16(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* noundef "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %9 = alloca %"struct.metal::array", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = alloca %"struct.metal::array", align 4
  %19 = alloca %"struct.metal::array", align 4
  %20 = alloca %"struct.metal::array", align 4
  %21 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %22 = alloca i8, i64 %21, align 8
  %23 = alloca i8, i64 %21, align 8
  %24 = tail call i64 @_ZN5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #8
  %25 = alloca i8, i64 %24, align 8
  %26 = alloca i8, i64 %21, align 8
  %27 = alloca i8, i64 %21, align 8
  %28 = alloca i8, i64 %24, align 8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %29 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !81, !noalias !84
  %30 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !90, !noalias !91
  %31 = bitcast i8* %22 to %struct._tensor_t*
  %32 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %32) #8
  %33 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 %29, i32* %33, align 4, !tbaa !28
  %34 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %30, i32* %34, align 4, !tbaa !28
  %35 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %35) #8
  %36 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 1, i32* %36, align 4, !tbaa !28
  %37 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %29, i32* %37, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %31, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %32, i8* nocapture nonnull readonly %35, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %35) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %32) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %23)
  %38 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !92, !noalias !93
  %39 = bitcast i8* %23 to %struct._tensor_t*
  %40 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %40) #8
  %41 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 %38, i32* %41, align 4, !tbaa !28
  %42 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %29, i32* %42, align 4, !tbaa !28
  %43 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %43) #8
  %44 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 1, i32* %44, align 4, !tbaa !28
  %45 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %38, i32* %45, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %39, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %40, i8* nocapture nonnull readonly %43, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %43) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %40) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %25)
  %46 = bitcast i8* %25 to %struct._tensor_t*
  %47 = bitcast float addrspace(1)* %2 to i8 addrspace(1)*
  %48 = bitcast %"struct.metal::array"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %48) #8
  %49 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 0
  store i32 %38, i32* %49, align 4, !tbaa !28
  %50 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %9, i64 0, i32 0, i64 1
  store i32 %30, i32* %50, align 4, !tbaa !28
  %51 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %51) #8
  %52 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 1, i32* %52, align 4, !tbaa !28
  %53 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %38, i32* %53, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %46, i16 2, i8 addrspace(1)* readnone %47, i8* nocapture nonnull readonly %48, i8* nocapture nonnull readonly %51, i8 0, i8 addrspace(1)* readnone null, i32 0, i8 -1) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %51) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %48) #8
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %26)
  %54 = extractelement <2 x i32> %6, i64 1
  %55 = shl i32 %54, 6
  %56 = bitcast %"struct.metal::array"* %19 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %56) #8, !noalias !94
  %57 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 0
  store i32 0, i32* %57, align 4, !tbaa !28, !noalias !94
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %19, i64 0, i32 0, i64 1
  store i32 %55, i32* %58, align 4, !tbaa !28, !noalias !94
  %59 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %59) #8
  %60 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %31, i16 2, i16 0, i16 0) #9
  %61 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %31, i16 2, i16 1, i16 0) #9
  %62 = sub i32 %61, %55
  %63 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %60, i32* %63, align 4
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %62, i32* %64, align 4
  %65 = bitcast i8* %26 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %65, %struct._tensor_t* nocapture nonnull readonly %31, i16 2, i8* nocapture nonnull readonly %56, i8* nocapture nonnull readonly %59) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %59) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %56) #8, !noalias !94
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %27)
  %66 = extractelement <2 x i32> %6, i64 0
  %67 = shl i32 %66, 5
  %68 = bitcast %"struct.metal::array"* %18 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %68) #8, !noalias !97
  %69 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 0
  store i32 %67, i32* %69, align 4, !tbaa !28, !noalias !97
  %70 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %18, i64 0, i32 0, i64 1
  store i32 0, i32* %70, align 4, !tbaa !28, !noalias !97
  %71 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %71) #8
  %72 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %39, i16 2, i16 0, i16 0) #9
  %73 = sub i32 %72, %67
  %74 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %39, i16 2, i16 1, i16 0) #9
  %75 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %73, i32* %75, align 4
  %76 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 %74, i32* %76, align 4
  %77 = bitcast i8* %27 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %77, %struct._tensor_t* nocapture nonnull readonly %39, i16 2, i8* nocapture nonnull readonly %68, i8* nocapture nonnull readonly %71) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %71) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %68) #8, !noalias !97
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %28)
  %78 = bitcast %"struct.metal::array"* %20 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %78) #8, !noalias !100
  %79 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 0
  store i32 %67, i32* %79, align 4, !tbaa !28, !noalias !100
  %80 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %20, i64 0, i32 0, i64 1
  store i32 %55, i32* %80, align 4, !tbaa !28, !noalias !100
  %81 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %81) #8
  %82 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %46, i16 2, i16 0, i16 0) #9
  %83 = sub i32 %82, %67
  %84 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %46, i16 2, i16 1, i16 0) #9
  %85 = sub i32 %84, %55
  %86 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 %83, i32* %86, align 4
  %87 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %85, i32* %87, align 4
  %88 = bitcast i8* %28 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %88, %struct._tensor_t* nocapture nonnull readonly %46, i16 2, i8* nocapture nonnull readonly %78, i8* nocapture nonnull readonly %81) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %81) #8
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %78) #8, !noalias !100
  %89 = tail call i32 @air.get_simdgroup_size.i32() #10
  %90 = shl i32 %89, 2
  %91 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %8 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %91) #8
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %91, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #8, !tbaa.struct !54
  call void @__tensorops_impl_matmul2d_op_run_dv_f16_dv_f16_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %8, i8* noundef nonnull %26, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %27, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %28, i32 noundef 2, i32 noundef -1, i32 noundef -1, i32 noundef %90) #11
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %91) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %28) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %27) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %26) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %25) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %23) #8
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #8
  ret void
}

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture writeonly, i16, i8 addrspace(1)* readnone, i8* nocapture readonly, i8* nocapture readonly, i8, i8 addrspace(1)* readnone, i32, i8) local_unnamed_addr #5

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture readonly, i16, i16, i16) local_unnamed_addr #5

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture writeonly, %struct._tensor_t* nocapture readonly, i16, i8* nocapture readonly, i8* nocapture readonly) local_unnamed_addr #5

; Function Attrs: argmemonly mustprogress nofree nounwind willreturn
declare void @llvm.memcpy.p0i8.p0i8.i64(i8* noalias nocapture writeonly, i8* noalias nocapture readonly, i64, i1 immarg) #6

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_dv_fp8e4m3_dv_fp8e4m3_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare i32 @air.get_simdgroup_size.i32() local_unnamed_addr #3

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_dv_f16_dv_fp8e4m3_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_dv_f16_dv_f16_dv_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

attributes #0 = { convergent nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="64" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #1 = { mustprogress nofree nosync readnone speculatable willreturn "deferred-static-alloca-size" }
attributes #2 = { mustprogress nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #3 = { mustprogress nofree nosync nounwind readnone willreturn }
attributes #4 = { argmemonly mustprogress nocallback nofree nosync nounwind willreturn }
attributes #5 = { argmemonly mustprogress nounwind willreturn }
attributes #6 = { argmemonly mustprogress nofree nounwind willreturn }
attributes #7 = { convergent "approx-func-fp-math"="true" "frame-pointer"="all" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #8 = { nounwind }
attributes #9 = { argmemonly nounwind willreturn }
attributes #10 = { nounwind readnone willreturn }
attributes #11 = { convergent nobuiltin nounwind "no-builtins" }
attributes #12 = { nobuiltin "no-builtins" }

!llvm.module.flags = !{!0, !1, !2, !3, !4, !5, !6, !7, !8}
!air.kernel = !{!9, !19, !20}
!air.compile_options = !{!21, !22, !23}
!llvm.ident = !{!24}
!air.version = !{!25}
!air.language_version = !{!26}
!air.source_file_name = !{!27}

!0 = !{i32 2, !"SDK Version", [2 x i32] [i32 27, i32 0]}
!1 = !{i32 1, !"wchar_size", i32 4}
!2 = !{i32 7, !"frame-pointer", i32 2}
!3 = !{i32 7, !"air.max_device_buffers", i32 31}
!4 = !{i32 7, !"air.max_constant_buffers", i32 31}
!5 = !{i32 7, !"air.max_threadgroup_buffers", i32 31}
!6 = !{i32 7, !"air.max_textures", i32 128}
!7 = !{i32 7, !"air.max_read_write_textures", i32 8}
!8 = !{i32 7, !"air.max_samplers", i32 16}
!9 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_f8, !10, !11}
!10 = !{}
!11 = !{!12, !13, !14, !15, !16, !17, !18}
!12 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_name", !"void", !"air.arg_name", !"A"}
!13 = !{i32 1, !"air.buffer", !"air.location_index", i32 1, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_name", !"void", !"air.arg_name", !"B"}
!14 = !{i32 2, !"air.buffer", !"air.location_index", i32 2, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"float", !"air.arg_name", !"C"}
!15 = !{i32 3, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 3, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"M"}
!16 = !{i32 4, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 4, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"N"}
!17 = !{i32 5, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 5, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"K"}
!18 = !{i32 6, !"air.threadgroup_position_in_grid", !"air.arg_type_name", !"uint2", !"air.arg_name", !"tgid"}
!19 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_mix8, !10, !11}
!20 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_f16, !10, !11}
!21 = !{!"air.compile.denorms_disable"}
!22 = !{!"air.compile.fast_math_enable"}
!23 = !{!"air.compile.framebuffer_fetch_enable"}
!24 = !{!"Apple metal version 32023.921 (metalfe-32023.921.6)"}
!25 = !{i32 2, i32 9, i32 0}
!26 = !{!"Metal", i32 4, i32 1, i32 0}
!27 = !{!"/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/raw/s0-20261026T131851Z/fp8_kernels.metal"}
!28 = !{!29, !29, i64 0}
!29 = !{!"int", !30, i64 0}
!30 = !{!"omnipotent char", !31, i64 0}
!31 = !{!"Simple C++ TBAA"}
!32 = !{!33}
!33 = distinct !{!33, !34, !"air-alias-scope-arg(5)"}
!34 = distinct !{!34, !"air-alias-scopes(mm_f8)"}
!35 = !{!36, !37, !38, !39, !40}
!36 = distinct !{!36, !34, !"air-alias-scope-arg(0)"}
!37 = distinct !{!37, !34, !"air-alias-scope-arg(1)"}
!38 = distinct !{!38, !34, !"air-alias-scope-arg(2)"}
!39 = distinct !{!39, !34, !"air-alias-scope-arg(3)"}
!40 = distinct !{!40, !34, !"air-alias-scope-arg(4)"}
!41 = !{!39}
!42 = !{!36, !37, !38, !40, !33}
!43 = !{!40}
!44 = !{!36, !37, !38, !39, !33}
!45 = !{!46}
!46 = distinct !{!46, !47, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!47 = distinct !{!47, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!48 = !{!49}
!49 = distinct !{!49, !50, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!50 = distinct !{!50, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!51 = !{!52}
!52 = distinct !{!52, !53, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!53 = distinct !{!53, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!54 = !{i64 0, i64 4, !28, i64 4, i64 4, !28, i64 8, i64 4, !28, i64 12, i64 1, !55, i64 13, i64 1, !55, i64 14, i64 1, !55, i64 16, i64 4, !57}
!55 = !{!56, !56, i64 0}
!56 = !{!"bool", !30, i64 0}
!57 = !{!58, !58, i64 0}
!58 = !{!"_ZTSN3mpp10tensor_ops19matmul2d_descriptor4modeE", !30, i64 0}
!59 = !{!60}
!60 = distinct !{!60, !61, !"air-alias-scope-arg(5)"}
!61 = distinct !{!61, !"air-alias-scopes(mm_mix8)"}
!62 = !{!63, !64, !65, !66, !67}
!63 = distinct !{!63, !61, !"air-alias-scope-arg(0)"}
!64 = distinct !{!64, !61, !"air-alias-scope-arg(1)"}
!65 = distinct !{!65, !61, !"air-alias-scope-arg(2)"}
!66 = distinct !{!66, !61, !"air-alias-scope-arg(3)"}
!67 = distinct !{!67, !61, !"air-alias-scope-arg(4)"}
!68 = !{!66}
!69 = !{!63, !64, !65, !67, !60}
!70 = !{!67}
!71 = !{!63, !64, !65, !66, !60}
!72 = !{!73}
!73 = distinct !{!73, !74, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!74 = distinct !{!74, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!75 = !{!76}
!76 = distinct !{!76, !77, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!77 = distinct !{!77, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!78 = !{!79}
!79 = distinct !{!79, !80, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!80 = distinct !{!80, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!81 = !{!82}
!82 = distinct !{!82, !83, !"air-alias-scope-arg(5)"}
!83 = distinct !{!83, !"air-alias-scopes(mm_f16)"}
!84 = !{!85, !86, !87, !88, !89}
!85 = distinct !{!85, !83, !"air-alias-scope-arg(0)"}
!86 = distinct !{!86, !83, !"air-alias-scope-arg(1)"}
!87 = distinct !{!87, !83, !"air-alias-scope-arg(2)"}
!88 = distinct !{!88, !83, !"air-alias-scope-arg(3)"}
!89 = distinct !{!89, !83, !"air-alias-scope-arg(4)"}
!90 = !{!88}
!91 = !{!85, !86, !87, !89, !82}
!92 = !{!89}
!93 = !{!85, !86, !87, !88, !82}
!94 = !{!95}
!95 = distinct !{!95, !96, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!96 = distinct !{!96, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!97 = !{!98}
!98 = distinct !{!98, !99, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!99 = distinct !{!99, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!100 = !{!101}
!101 = distinct !{!101, !102, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!102 = distinct !{!102, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdevicefNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjjEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
