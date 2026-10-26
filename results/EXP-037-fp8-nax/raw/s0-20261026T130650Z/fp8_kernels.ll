; ModuleID = '/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/harness/../raw/s0-20261026T130650Z/fp8_kernels.metal'
source_filename = "/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/harness/../raw/s0-20261026T130650Z/fp8_kernels.metal"
target datalayout = "e-p:64:64:64-i1:8:8-i8:8:8-i16:16:16-i32:32:32-i64:64:64-f32:32:32-f64:64:64-v16:16:16-v24:32:32-v32:32:32-v48:64:64-v64:64:64-v96:128:128-v128:128:128-v192:256:256-v256:256:256-v512:512:512-v1024:1024:1024-n8:16:32"
target triple = "air64_v29-apple-macosx27.0.0"

%"struct.mpp::tensor_ops::matmul2d_descriptor" = type { i32, i32, i32, i8, i8, i8, i32 }
%"struct.metal::array" = type { [2 x i32] }
%struct._tensor_t = type opaque

@_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE = linkonce_odr local_unnamed_addr constant %"struct.mpp::tensor_ops::matmul2d_descriptor" { i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0 }

; Function Attrs: convergent nounwind
define void @mm_f16(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca [2 x i32], align 4
  %9 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #9
  %19 = alloca i8, i64 %18, align 8
  %20 = alloca i8, i64 %18, align 8
  %21 = alloca i8, i64 %18, align 8
  %22 = alloca i8, i64 %18, align 8
  %23 = tail call i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEEDhDhfiJEEEEE.MTL_SIZEAS() #9
  %24 = alloca i8, i64 %23, align 4
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %19)
  %25 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !32, !noalias !35
  %26 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !41, !noalias !42
  %27 = bitcast i8* %19 to %struct._tensor_t*
  %28 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %28) #9
  %29 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 %25, i32* %29, align 4, !tbaa !28
  %30 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %26, i32* %30, align 4, !tbaa !28
  %31 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %31) #9
  %32 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 1, i32* %32, align 4, !tbaa !28
  %33 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %25, i32* %33, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %27, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %28, i8* nocapture nonnull readonly %31, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %31) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %28) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %20)
  %34 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !43, !noalias !44
  %35 = bitcast i8* %20 to %struct._tensor_t*
  %36 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %36) #9
  %37 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 %34, i32* %37, align 4, !tbaa !28
  %38 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %25, i32* %38, align 4, !tbaa !28
  %39 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %39) #9
  %40 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 1, i32* %40, align 4, !tbaa !28
  %41 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %34, i32* %41, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %35, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %36, i8* nocapture nonnull readonly %39, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %39) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %36) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %21)
  %42 = extractelement <2 x i32> %6, i64 1
  %43 = shl i32 %42, 6
  %44 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %44) #9, !noalias !45
  %45 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 0, i32* %45, align 4, !tbaa !28, !noalias !45
  %46 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %43, i32* %46, align 4, !tbaa !28, !noalias !45
  %47 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %47) #9
  %48 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %27, i16 2, i16 0, i16 0) #10
  %49 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %27, i16 2, i16 1, i16 0) #10
  %50 = sub i32 %49, %43
  %51 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 %48, i32* %51, align 4
  %52 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %50, i32* %52, align 4
  %53 = bitcast i8* %21 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %53, %struct._tensor_t* nocapture nonnull readonly %27, i16 2, i8* nocapture nonnull readonly %44, i8* nocapture nonnull readonly %47) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %47) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %44) #9, !noalias !45
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %54 = extractelement <2 x i32> %6, i64 0
  %55 = shl i32 %54, 5
  %56 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %56) #9, !noalias !48
  %57 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %55, i32* %57, align 4, !tbaa !28, !noalias !48
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 0, i32* %58, align 4, !tbaa !28, !noalias !48
  %59 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %59) #9
  %60 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %35, i16 2, i16 0, i16 0) #10
  %61 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %35, i16 2, i16 1, i16 0) #10
  %62 = sub i32 %60, %55
  %63 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %62, i32* %63, align 4
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %61, i32* %64, align 4
  %65 = bitcast i8* %22 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %65, %struct._tensor_t* nocapture nonnull readonly %35, i16 2, i8* nocapture nonnull readonly %56, i8* nocapture nonnull readonly %59) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %59) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %56) #9, !noalias !48
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %24)
  %66 = tail call i32 @air.get_simdgroup_size.i32() #11
  %67 = shl i32 %66, 2
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_init(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488, i32 noundef %67) #12
  br label %68

68:                                               ; preds = %85, %7
  %69 = phi i16 [ 0, %7 ], [ %86, %85 ]
  %70 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435472, i32 noundef 268435472, i32 noundef %67) #12
  %71 = icmp ult i16 %69, %70
  br i1 %71, label %80, label %72

72:                                               ; preds = %68
  %73 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %73) #9
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %73, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #9, !tbaa.struct !51
  %74 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext -1, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488) #12
  call void @__tensorops_impl_matmul2d_op_run_cooperative_dv_f16_dv_f16_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %9, i8* noundef nonnull %21, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %22, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef %74, i32 noundef %67) #12
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %73) #9
  %75 = bitcast [2 x i32]* %8 to i8*
  %76 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 0
  %77 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 1
  %78 = zext i32 %34 to i64
  %79 = zext i32 %55 to i64
  br label %87

80:                                               ; preds = %68
  %81 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %69, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488, i32 noundef %67) #12
  br i1 %81, label %82, label %85

82:                                               ; preds = %80
  %83 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %69, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488) #12
  %84 = bitcast i8* %83 to float*
  store float 0.000000e+00, float* %84, align 4, !tbaa !56
  br label %85

85:                                               ; preds = %80, %82
  %86 = add nuw i16 %69, 1
  br label %68, !llvm.loop !58

87:                                               ; preds = %107, %72
  %88 = phi i16 [ 0, %72 ], [ %108, %107 ]
  %89 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435472, i32 noundef 268435472, i32 noundef %67) #12
  %90 = icmp ult i16 %88, %89
  br i1 %90, label %92, label %91

91:                                               ; preds = %87
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %24) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %21) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %20) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %19) #9
  ret void

92:                                               ; preds = %87
  %93 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488, i32 noundef %67) #12
  br i1 %93, label %94, label %107

94:                                               ; preds = %92
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %75) #9
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_get_coordinate(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i8* noundef nonnull %75, i32 noundef 536870944, i32 noundef %67, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488) #12
  %95 = load i32, i32* %76, align 4, !tbaa !28
  %96 = load i32, i32* %77, align 4, !tbaa !28
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %75) #9
  %97 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488) #12
  %98 = bitcast i8* %97 to float*
  %99 = load float, float* %98, align 4, !tbaa !56
  %100 = add i32 %95, %43
  %101 = zext i32 %100 to i64
  %102 = mul nuw i64 %101, %78
  %103 = sext i32 %96 to i64
  %104 = add nsw i64 %103, %79
  %105 = add i64 %104, %102
  %106 = getelementptr inbounds float, float addrspace(1)* %2, i64 %105
  store float %99, float addrspace(1)* %106, align 4, !tbaa !56, !alias.scope !60, !noalias !61
  br label %107

107:                                              ; preds = %92, %94
  %108 = add nuw i16 %88, 1
  br label %87, !llvm.loop !62
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() #13
  %2 = trunc i64 %1 to i16
  %3 = tail call i16 @air.get_descriptor_size_tensor(i16 %2, i16 4) #11
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
define linkonce_odr hidden i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEEDhDhfiJEEEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEEDhDhfiJEE19thread_storage_sizeEv() #14
  ret i64 %1
}

; Function Attrs: convergent nounwind
define linkonce_odr i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEEDhDhfiJEE19thread_storage_sizeEv() local_unnamed_addr #5 align 2 {
  %1 = tail call i32 @air.get_simdgroup_size.i32() #11
  %2 = shl i32 %1, 2
  %3 = tail call i64 @__tensorops_impl_matmul2d_op_cooperative_tensor_data_size(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i32 noundef 268435472, i32 noundef 268435472, i32 noundef 268435488, i32 noundef %2) #12
  ret i64 %3
}

; Function Attrs: convergent nounwind
define void @mm_f8(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca [2 x i32], align 4
  %9 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #9
  %19 = alloca i8, i64 %18, align 8
  %20 = alloca i8, i64 %18, align 8
  %21 = alloca i8, i64 %18, align 8
  %22 = alloca i8, i64 %18, align 8
  %23 = tail call i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEENS_21metal_fp8_e4m3_formatESB_fiJEEEEE.MTL_SIZEAS() #9
  %24 = alloca i8, i64 %23, align 4
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %19)
  %25 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !63, !noalias !66
  %26 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !72, !noalias !73
  %27 = bitcast i8* %19 to %struct._tensor_t*
  %28 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %28) #9
  %29 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 %25, i32* %29, align 4, !tbaa !28
  %30 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %26, i32* %30, align 4, !tbaa !28
  %31 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %31) #9
  %32 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 1, i32* %32, align 4, !tbaa !28
  %33 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %25, i32* %33, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %27, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %28, i8* nocapture nonnull readonly %31, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %31) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %28) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %20)
  %34 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !74, !noalias !75
  %35 = bitcast i8* %20 to %struct._tensor_t*
  %36 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %36) #9
  %37 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 %34, i32* %37, align 4, !tbaa !28
  %38 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %25, i32* %38, align 4, !tbaa !28
  %39 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %39) #9
  %40 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 1, i32* %40, align 4, !tbaa !28
  %41 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %34, i32* %41, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %35, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %36, i8* nocapture nonnull readonly %39, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %39) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %36) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %21)
  %42 = extractelement <2 x i32> %6, i64 1
  %43 = shl i32 %42, 6
  %44 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %44) #9, !noalias !76
  %45 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 0, i32* %45, align 4, !tbaa !28, !noalias !76
  %46 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %43, i32* %46, align 4, !tbaa !28, !noalias !76
  %47 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %47) #9
  %48 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %27, i16 2, i16 0, i16 0) #10
  %49 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %27, i16 2, i16 1, i16 0) #10
  %50 = sub i32 %49, %43
  %51 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 %48, i32* %51, align 4
  %52 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %50, i32* %52, align 4
  %53 = bitcast i8* %21 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %53, %struct._tensor_t* nocapture nonnull readonly %27, i16 2, i8* nocapture nonnull readonly %44, i8* nocapture nonnull readonly %47) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %47) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %44) #9, !noalias !76
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %54 = extractelement <2 x i32> %6, i64 0
  %55 = shl i32 %54, 5
  %56 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %56) #9, !noalias !79
  %57 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %55, i32* %57, align 4, !tbaa !28, !noalias !79
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 0, i32* %58, align 4, !tbaa !28, !noalias !79
  %59 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %59) #9
  %60 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %35, i16 2, i16 0, i16 0) #10
  %61 = sub i32 %60, %55
  %62 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %35, i16 2, i16 1, i16 0) #10
  %63 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %61, i32* %63, align 4
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %62, i32* %64, align 4
  %65 = bitcast i8* %22 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %65, %struct._tensor_t* nocapture nonnull readonly %35, i16 2, i8* nocapture nonnull readonly %56, i8* nocapture nonnull readonly %59) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %59) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %56) #9, !noalias !79
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %24)
  %66 = tail call i32 @air.get_simdgroup_size.i32() #11
  %67 = shl i32 %66, 2
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_init(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %67) #12
  br label %68

68:                                               ; preds = %85, %7
  %69 = phi i16 [ 0, %7 ], [ %86, %85 ]
  %70 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435464, i32 noundef 268435464, i32 noundef %67) #12
  %71 = icmp ult i16 %69, %70
  br i1 %71, label %80, label %72

72:                                               ; preds = %68
  %73 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %73) #9
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %73, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #9, !tbaa.struct !51
  %74 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext -1, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488) #12
  call void @__tensorops_impl_matmul2d_op_run_cooperative_dv_fp8e4m3_dv_fp8e4m3_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %9, i8* noundef nonnull %21, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %22, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef %74, i32 noundef %67) #12
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %73) #9
  %75 = bitcast [2 x i32]* %8 to i8*
  %76 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 0
  %77 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 1
  %78 = zext i32 %34 to i64
  %79 = zext i32 %55 to i64
  br label %87

80:                                               ; preds = %68
  %81 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %69, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %67) #12
  br i1 %81, label %82, label %85

82:                                               ; preds = %80
  %83 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %69, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488) #12
  %84 = bitcast i8* %83 to float*
  store float 0.000000e+00, float* %84, align 4, !tbaa !56
  br label %85

85:                                               ; preds = %80, %82
  %86 = add nuw i16 %69, 1
  br label %68, !llvm.loop !82

87:                                               ; preds = %107, %72
  %88 = phi i16 [ 0, %72 ], [ %108, %107 ]
  %89 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i32 noundef 268435464, i32 noundef 268435464, i32 noundef %67) #12
  %90 = icmp ult i16 %88, %89
  br i1 %90, label %92, label %91

91:                                               ; preds = %87
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %24) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %21) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %20) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %19) #9
  ret void

92:                                               ; preds = %87
  %93 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %67) #12
  br i1 %93, label %94, label %107

94:                                               ; preds = %92
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %75) #9
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_get_coordinate(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i8* noundef nonnull %75, i32 noundef 536870944, i32 noundef %67, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488) #12
  %95 = load i32, i32* %76, align 4, !tbaa !28
  %96 = load i32, i32* %77, align 4, !tbaa !28
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %75) #9
  %97 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %24, i16 noundef zeroext %88, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488) #12
  %98 = bitcast i8* %97 to float*
  %99 = load float, float* %98, align 4, !tbaa !56
  %100 = add i32 %95, %43
  %101 = zext i32 %100 to i64
  %102 = mul nuw i64 %101, %78
  %103 = sext i32 %96 to i64
  %104 = add nsw i64 %103, %79
  %105 = add i64 %104, %102
  %106 = getelementptr inbounds float, float addrspace(1)* %2, i64 %105
  store float %99, float addrspace(1)* %106, align 4, !tbaa !56, !alias.scope !83, !noalias !84
  br label %107

107:                                              ; preds = %92, %94
  %108 = add nuw i16 %88, 1
  br label %87, !llvm.loop !85
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN5metal15__tensor_detail21__tensor_safe_extentsINS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEvE4rankEv() #13
  %2 = trunc i64 %1 to i16
  %3 = tail call i16 @air.get_descriptor_size_tensor(i16 %2, i16 4) #11
  %4 = zext i16 %3 to i64
  ret i64 %4
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEENS_21metal_fp8_e4m3_formatESB_fiJEEEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEENS5_21metal_fp8_e4m3_formatES8_fiJEE19thread_storage_sizeEv() #14
  ret i64 %1
}

; Function Attrs: convergent nounwind
define linkonce_odr i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEENS5_21metal_fp8_e4m3_formatES8_fiJEE19thread_storage_sizeEv() local_unnamed_addr #5 align 2 {
  %1 = tail call i32 @air.get_simdgroup_size.i32() #11
  %2 = shl i32 %1, 2
  %3 = tail call i64 @__tensorops_impl_matmul2d_op_cooperative_tensor_data_size(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i32 noundef 268435464, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %2) #12
  ret i64 %3
}

; Function Attrs: convergent nounwind
define void @mm_mix8(i8 addrspace(1)* noundef "air-buffer-no-alias" %0, i8 addrspace(1)* noundef "air-buffer-no-alias" %1, float addrspace(1)* nocapture noundef writeonly "air-buffer-no-alias" %2, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %3, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %4, i32 addrspace(2)* nocapture noundef readonly align 4 dereferenceable(4) "air-buffer-no-alias" %5, <2 x i32> noundef %6) local_unnamed_addr #0 {
  %8 = alloca [2 x i32], align 4
  %9 = alloca %"struct.mpp::tensor_ops::matmul2d_descriptor", align 4
  %10 = alloca %"struct.metal::array", align 4
  %11 = alloca %"struct.metal::array", align 4
  %12 = alloca %"struct.metal::array", align 4
  %13 = alloca %"struct.metal::array", align 4
  %14 = alloca %"struct.metal::array", align 4
  %15 = alloca %"struct.metal::array", align 4
  %16 = alloca %"struct.metal::array", align 4
  %17 = alloca %"struct.metal::array", align 4
  %18 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #9
  %19 = alloca i8, i64 %18, align 8
  %20 = tail call i64 @_ZN5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEEE.MTL_SIZEAS() #9
  %21 = alloca i8, i64 %20, align 8
  %22 = alloca i8, i64 %18, align 8
  %23 = alloca i8, i64 %20, align 8
  %24 = tail call i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEEDhNS_21metal_fp8_e4m3_formatEfiJEEEEE.MTL_SIZEAS() #9
  %25 = alloca i8, i64 %24, align 4
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %19)
  %26 = load i32, i32 addrspace(2)* %5, align 4, !tbaa !28, !alias.scope !86, !noalias !89
  %27 = load i32, i32 addrspace(2)* %3, align 4, !tbaa !28, !alias.scope !95, !noalias !96
  %28 = bitcast i8* %19 to %struct._tensor_t*
  %29 = bitcast %"struct.metal::array"* %12 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %29) #9
  %30 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 0
  store i32 %26, i32* %30, align 4, !tbaa !28
  %31 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %12, i64 0, i32 0, i64 1
  store i32 %27, i32* %31, align 4, !tbaa !28
  %32 = bitcast %"struct.metal::array"* %13 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %32) #9
  %33 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 0
  store i32 1, i32* %33, align 4, !tbaa !28
  %34 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %13, i64 0, i32 0, i64 1
  store i32 %26, i32* %34, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %28, i16 2, i8 addrspace(1)* readnone %0, i8* nocapture nonnull readonly %29, i8* nocapture nonnull readonly %32, i8 1, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %32) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %29) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %21)
  %35 = load i32, i32 addrspace(2)* %4, align 4, !tbaa !28, !alias.scope !97, !noalias !98
  %36 = bitcast i8* %21 to %struct._tensor_t*
  %37 = bitcast %"struct.metal::array"* %10 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %37) #9
  %38 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 0
  store i32 %35, i32* %38, align 4, !tbaa !28
  %39 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %10, i64 0, i32 0, i64 1
  store i32 %26, i32* %39, align 4, !tbaa !28
  %40 = bitcast %"struct.metal::array"* %11 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %40) #9
  %41 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 0
  store i32 1, i32* %41, align 4, !tbaa !28
  %42 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %11, i64 0, i32 0, i64 1
  store i32 %35, i32* %42, align 4, !tbaa !28
  call void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture nonnull writeonly %36, i16 2, i8 addrspace(1)* readnone %1, i8* nocapture nonnull readonly %37, i8* nocapture nonnull readonly %40, i8 25, i8 addrspace(1)* readnone null, i32 0, i8 -1) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %40) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %37) #9
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %22)
  %43 = extractelement <2 x i32> %6, i64 1
  %44 = shl i32 %43, 6
  %45 = bitcast %"struct.metal::array"* %17 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %45) #9, !noalias !99
  %46 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 0
  store i32 0, i32* %46, align 4, !tbaa !28, !noalias !99
  %47 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %17, i64 0, i32 0, i64 1
  store i32 %44, i32* %47, align 4, !tbaa !28, !noalias !99
  %48 = bitcast %"struct.metal::array"* %15 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %48) #9
  %49 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %28, i16 2, i16 0, i16 0) #10
  %50 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %28, i16 2, i16 1, i16 0) #10
  %51 = sub i32 %50, %44
  %52 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 0
  store i32 %49, i32* %52, align 4
  %53 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %15, i64 0, i32 0, i64 1
  store i32 %51, i32* %53, align 4
  %54 = bitcast i8* %22 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %54, %struct._tensor_t* nocapture nonnull readonly %28, i16 2, i8* nocapture nonnull readonly %45, i8* nocapture nonnull readonly %48) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %48) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %45) #9, !noalias !99
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %23)
  %55 = extractelement <2 x i32> %6, i64 0
  %56 = shl i32 %55, 5
  %57 = bitcast %"struct.metal::array"* %16 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %57) #9, !noalias !102
  %58 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 0
  store i32 %56, i32* %58, align 4, !tbaa !28, !noalias !102
  %59 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %16, i64 0, i32 0, i64 1
  store i32 0, i32* %59, align 4, !tbaa !28, !noalias !102
  %60 = bitcast %"struct.metal::array"* %14 to i8*
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %60) #9
  %61 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %36, i16 2, i16 0, i16 0) #10
  %62 = sub i32 %61, %56
  %63 = call i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture nonnull readonly %36, i16 2, i16 1, i16 0) #10
  %64 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 0
  store i32 %62, i32* %64, align 4
  %65 = getelementptr inbounds %"struct.metal::array", %"struct.metal::array"* %14, i64 0, i32 0, i64 1
  store i32 %63, i32* %65, align 4
  %66 = bitcast i8* %23 to %struct._tensor_t*
  call void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture nonnull writeonly %66, %struct._tensor_t* nocapture nonnull readonly %36, i16 2, i8* nocapture nonnull readonly %57, i8* nocapture nonnull readonly %60) #10
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %60) #9
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %57) #9, !noalias !102
  call void @llvm.lifetime.start.p0i8(i64 -1, i8* nonnull %25)
  %67 = tail call i32 @air.get_simdgroup_size.i32() #11
  %68 = shl i32 %67, 2
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_init(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %68) #12
  br label %69

69:                                               ; preds = %86, %7
  %70 = phi i16 [ 0, %7 ], [ %87, %86 ]
  %71 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i32 noundef 268435472, i32 noundef 268435464, i32 noundef %68) #12
  %72 = icmp ult i16 %70, %71
  br i1 %72, label %81, label %73

73:                                               ; preds = %69
  %74 = bitcast %"struct.mpp::tensor_ops::matmul2d_descriptor"* %9 to i8*
  call void @llvm.lifetime.start.p0i8(i64 20, i8* nonnull %74) #9
  call void @llvm.memcpy.p0i8.p0i8.i64(i8* noundef nonnull align 4 dereferenceable(20) %74, i8* noundef nonnull align 4 dereferenceable(20) bitcast (%"struct.mpp::tensor_ops::matmul2d_descriptor"* @_ZTAXtlN3mpp10tensor_ops19matmul2d_descriptorELi64ELi32ELin1EEE to i8*), i64 20, i1 false) #9, !tbaa.struct !51
  %75 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext -1, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488) #12
  call void @__tensorops_impl_matmul2d_op_run_cooperative_dv_f16_dv_fp8e4m3_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20) %9, i8* noundef nonnull %22, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef nonnull %23, i32 noundef 2, i32 noundef 0, i32 noundef 0, i32 noundef 0, i32 noundef -1, i32 noundef -1, i8* noundef %75, i32 noundef %68) #12
  call void @llvm.lifetime.end.p0i8(i64 20, i8* nonnull %74) #9
  %76 = bitcast [2 x i32]* %8 to i8*
  %77 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 0
  %78 = getelementptr inbounds [2 x i32], [2 x i32]* %8, i64 0, i64 1
  %79 = zext i32 %35 to i64
  %80 = zext i32 %56 to i64
  br label %88

81:                                               ; preds = %69
  %82 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext %70, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %68) #12
  br i1 %82, label %83, label %86

83:                                               ; preds = %81
  %84 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext %70, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488) #12
  %85 = bitcast i8* %84 to float*
  store float 0.000000e+00, float* %85, align 4, !tbaa !56
  br label %86

86:                                               ; preds = %81, %83
  %87 = add nuw i16 %70, 1
  br label %69, !llvm.loop !105

88:                                               ; preds = %108, %73
  %89 = phi i16 [ 0, %73 ], [ %109, %108 ]
  %90 = call zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i32 noundef 268435472, i32 noundef 268435464, i32 noundef %68) #12
  %91 = icmp ult i16 %89, %90
  br i1 %91, label %93, label %92

92:                                               ; preds = %88
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %25) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %23) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %22) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %21) #9
  call void @llvm.lifetime.end.p0i8(i64 -1, i8* nonnull %19) #9
  ret void

93:                                               ; preds = %88
  %94 = call zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext %89, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %68) #12
  br i1 %94, label %95, label %108

95:                                               ; preds = %93
  call void @llvm.lifetime.start.p0i8(i64 8, i8* nonnull %76) #9
  call void @__tensorops_impl_matmul2d_op_cooperative_tensor_get_coordinate(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext %89, i8* noundef nonnull %76, i32 noundef 536870944, i32 noundef %68, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488) #12
  %96 = load i32, i32* %77, align 4, !tbaa !28
  %97 = load i32, i32* %78, align 4, !tbaa !28
  call void @llvm.lifetime.end.p0i8(i64 8, i8* nonnull %76) #9
  %98 = call i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i8* noundef nonnull %25, i16 noundef zeroext %89, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488) #12
  %99 = bitcast i8* %98 to float*
  %100 = load float, float* %99, align 4, !tbaa !56
  %101 = add i32 %96, %44
  %102 = zext i32 %101 to i64
  %103 = mul nuw i64 %102, %79
  %104 = sext i32 %97 to i64
  %105 = add nsw i64 %104, %80
  %106 = add i64 %105, %103
  %107 = getelementptr inbounds float, float addrspace(1)* %2, i64 %106
  store float %100, float addrspace(1)* %107, align 4, !tbaa !56, !alias.scope !106, !noalias !107
  br label %108

108:                                              ; preds = %93, %95
  %109 = add nuw i16 %89, 1
  br label %88, !llvm.loop !108
}

; Function Attrs: mustprogress nofree nosync readnone speculatable willreturn
define linkonce_odr hidden i64 @_ZN5metal18cooperative_tensorIfNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEEN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS4_19matmul2d_descriptorELi64ELi32ELin1EEELNS5_36__matmul2d_cooperative_operand_indexE2ENS_20execution_simdgroupsILm4EEEDhNS_21metal_fp8_e4m3_formatEfiJEEEEE.MTL_SIZEAS() local_unnamed_addr #1 {
  %1 = tail call i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEEDhNS5_21metal_fp8_e4m3_formatEfiJEE19thread_storage_sizeEv() #14
  ret i64 %1
}

; Function Attrs: convergent nounwind
define linkonce_odr i64 @_ZN3mpp10tensor_ops17__mutmul2d_detail16__operand_layoutIXtlNS0_19matmul2d_descriptorELi64ELi32ELin1EEELNS1_36__matmul2d_cooperative_operand_indexE2EN5metal20execution_simdgroupsILm4EEEDhNS5_21metal_fp8_e4m3_formatEfiJEE19thread_storage_sizeEv() local_unnamed_addr #5 align 2 {
  %1 = tail call i32 @air.get_simdgroup_size.i32() #11
  %2 = shl i32 %1, 2
  %3 = tail call i64 @__tensorops_impl_matmul2d_op_cooperative_tensor_data_size(i32 noundef 2, i32 64, i32 32, i32 -1, i8 0, i8 0, i8 0, i32 0, i32 noundef 268435472, i32 noundef 268435464, i32 noundef 268435488, i32 noundef %2) #12
  ret i64 %3
}

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare void @air.init_strided_private_tensor.i32.global(%struct._tensor_t* nocapture writeonly, i16, i8 addrspace(1)* readnone, i8* nocapture readonly, i8* nocapture readonly, i8, i8 addrspace(1)* readnone, i32, i8) local_unnamed_addr #6

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare i32 @air.get_extent_private_tensor.i32(%struct._tensor_t* nocapture readonly, i16, i16, i16) local_unnamed_addr #6

; Function Attrs: argmemonly mustprogress nounwind willreturn
declare void @air.slice_private_tensor_private_tensor.s.i32(%struct._tensor_t* nocapture writeonly, %struct._tensor_t* nocapture readonly, i16, i8* nocapture readonly, i8* nocapture readonly) local_unnamed_addr #6

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_cooperative_tensor_init(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: mustprogress nofree nosync nounwind readnone willreturn
declare i32 @air.get_simdgroup_size.i32() local_unnamed_addr #3

; Function Attrs: convergent
declare i64 @__tensorops_impl_matmul2d_op_cooperative_tensor_data_size(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare zeroext i16 @__tensorops_impl_matmul2d_op_cooperative_tensor_num_elements(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i8* noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare zeroext i1 @__tensorops_impl_matmul2d_op_cooperative_tensor_is_valid_element(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i8* noundef, i16 noundef zeroext, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare i8* @__tensorops_impl_matmul2d_op_cooperative_tensor_get_element_pointer(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i8* noundef, i16 noundef zeroext, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: argmemonly mustprogress nofree nounwind willreturn
declare void @llvm.memcpy.p0i8.p0i8.i64(i8* noalias nocapture writeonly, i8* noalias nocapture readonly, i64, i1 immarg) #8

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_cooperative_dv_f16_dv_f16_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_cooperative_tensor_get_coordinate(i32 noundef, i32, i32, i32, i8, i8, i8, i32, i8* noundef, i16 noundef zeroext, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_cooperative_dv_fp8e4m3_dv_fp8e4m3_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

; Function Attrs: convergent
declare void @__tensorops_impl_matmul2d_op_run_cooperative_dv_f16_dv_fp8e4m3_f32_v2(%"struct.mpp::tensor_ops::matmul2d_descriptor"* noundef nonnull align 4 dereferenceable(20), i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i32 noundef, i8* noundef, i32 noundef) local_unnamed_addr #7 section "air.externally_defined"

attributes #0 = { convergent nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="64" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #1 = { mustprogress nofree nosync readnone speculatable willreturn "deferred-static-alloca-size" }
attributes #2 = { mustprogress nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #3 = { mustprogress nofree nosync nounwind readnone willreturn }
attributes #4 = { argmemonly mustprogress nocallback nofree nosync nounwind willreturn }
attributes #5 = { convergent nounwind "approx-func-fp-math"="true" "frame-pointer"="all" "min-legal-vector-width"="0" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #6 = { argmemonly mustprogress nounwind willreturn }
attributes #7 = { convergent "approx-func-fp-math"="true" "frame-pointer"="all" "no-builtins" "no-infs-fp-math"="true" "no-nans-fp-math"="true" "no-signed-zeros-fp-math"="true" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "unsafe-fp-math"="true" }
attributes #8 = { argmemonly mustprogress nofree nounwind willreturn }
attributes #9 = { nounwind }
attributes #10 = { argmemonly nounwind willreturn }
attributes #11 = { nounwind readnone willreturn }
attributes #12 = { convergent nobuiltin nounwind "no-builtins" }
attributes #13 = { nobuiltin "no-builtins" }
attributes #14 = { convergent nobuiltin "no-builtins" }

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
!9 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_f16, !10, !11}
!10 = !{}
!11 = !{!12, !13, !14, !15, !16, !17, !18}
!12 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_name", !"void", !"air.arg_name", !"A"}
!13 = !{i32 1, !"air.buffer", !"air.location_index", i32 1, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_name", !"void", !"air.arg_name", !"B"}
!14 = !{i32 2, !"air.buffer", !"air.location_index", i32 2, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"float", !"air.arg_name", !"C"}
!15 = !{i32 3, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 3, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"M"}
!16 = !{i32 4, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 4, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"N"}
!17 = !{i32 5, !"air.buffer", !"air.buffer_size", i32 4, !"air.location_index", i32 5, i32 1, !"air.read", !"air.address_space", i32 2, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"K"}
!18 = !{i32 6, !"air.threadgroup_position_in_grid", !"air.arg_type_name", !"uint2", !"air.arg_name", !"tgid"}
!19 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_f8, !10, !11}
!20 = !{void (i8 addrspace(1)*, i8 addrspace(1)*, float addrspace(1)*, i32 addrspace(2)*, i32 addrspace(2)*, i32 addrspace(2)*, <2 x i32>)* @mm_mix8, !10, !11}
!21 = !{!"air.compile.denorms_disable"}
!22 = !{!"air.compile.fast_math_enable"}
!23 = !{!"air.compile.framebuffer_fetch_enable"}
!24 = !{!"Apple metal version 32023.921 (metalfe-32023.921.6)"}
!25 = !{i32 2, i32 9, i32 0}
!26 = !{!"Metal", i32 4, i32 1, i32 0}
!27 = !{!"/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-037-fp8-nax/raw/s0-20261026T130650Z/fp8_kernels.metal"}
!28 = !{!29, !29, i64 0}
!29 = !{!"int", !30, i64 0}
!30 = !{!"omnipotent char", !31, i64 0}
!31 = !{!"Simple C++ TBAA"}
!32 = !{!33}
!33 = distinct !{!33, !34, !"air-alias-scope-arg(5)"}
!34 = distinct !{!34, !"air-alias-scopes(mm_f16)"}
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
!46 = distinct !{!46, !47, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!47 = distinct !{!47, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!48 = !{!49}
!49 = distinct !{!49, !50, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!50 = distinct !{!50, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!51 = !{i64 0, i64 4, !28, i64 4, i64 4, !28, i64 8, i64 4, !28, i64 12, i64 1, !52, i64 13, i64 1, !52, i64 14, i64 1, !52, i64 16, i64 4, !54}
!52 = !{!53, !53, i64 0}
!53 = !{!"bool", !30, i64 0}
!54 = !{!55, !55, i64 0}
!55 = !{!"_ZTSN3mpp10tensor_ops19matmul2d_descriptor4modeE", !30, i64 0}
!56 = !{!57, !57, i64 0}
!57 = !{!"float", !30, i64 0}
!58 = distinct !{!58, !59}
!59 = !{!"llvm.loop.mustprogress"}
!60 = !{!38}
!61 = !{!36, !37, !39, !40, !33}
!62 = distinct !{!62, !59}
!63 = !{!64}
!64 = distinct !{!64, !65, !"air-alias-scope-arg(5)"}
!65 = distinct !{!65, !"air-alias-scopes(mm_f8)"}
!66 = !{!67, !68, !69, !70, !71}
!67 = distinct !{!67, !65, !"air-alias-scope-arg(0)"}
!68 = distinct !{!68, !65, !"air-alias-scope-arg(1)"}
!69 = distinct !{!69, !65, !"air-alias-scope-arg(2)"}
!70 = distinct !{!70, !65, !"air-alias-scope-arg(3)"}
!71 = distinct !{!71, !65, !"air-alias-scope-arg(4)"}
!72 = !{!70}
!73 = !{!67, !68, !69, !71, !64}
!74 = !{!71}
!75 = !{!67, !68, !69, !70, !64}
!76 = !{!77}
!77 = distinct !{!77, !78, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!78 = distinct !{!78, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!79 = !{!80}
!80 = distinct !{!80, !81, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!81 = distinct !{!81, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!82 = distinct !{!82, !59}
!83 = !{!69}
!84 = !{!67, !68, !70, !71, !64}
!85 = distinct !{!85, !59}
!86 = !{!87}
!87 = distinct !{!87, !88, !"air-alias-scope-arg(5)"}
!88 = distinct !{!88, !"air-alias-scopes(mm_mix8)"}
!89 = !{!90, !91, !92, !93, !94}
!90 = distinct !{!90, !88, !"air-alias-scope-arg(0)"}
!91 = distinct !{!91, !88, !"air-alias-scope-arg(1)"}
!92 = distinct !{!92, !88, !"air-alias-scope-arg(2)"}
!93 = distinct !{!93, !88, !"air-alias-scope-arg(3)"}
!94 = distinct !{!94, !88, !"air-alias-scope-arg(4)"}
!95 = !{!93}
!96 = !{!90, !91, !92, !94, !87}
!97 = !{!94}
!98 = !{!90, !91, !92, !93, !87}
!99 = !{!100}
!100 = distinct !{!100, !101, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_: argument 0"}
!101 = distinct !{!101, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceDhNS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJijEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS5_vE8get_rankEvEEES5_E4typeEDpS8_"}
!102 = !{!103}
!103 = distinct !{!103, !104, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_: argument 0"}
!104 = distinct !{!104, !"_ZNU9MTLthreadK5metal6tensorIU9MTLdeviceNS_21metal_fp8_e4m3_formatENS_7extentsIiJLm18446744073709551615ELm18446744073709551615EEEENS_13tensor_inlineEJEE5sliceIJjiEEENS_9enable_ifIXaafraa16is_convertible_vIT_iEeqsZT_clL_ZNS_13__tensor_baseIS6_vE8get_rankEvEEES6_E4typeEDpS9_"}
!105 = distinct !{!105, !59}
!106 = !{!92}
!107 = !{!90, !91, !93, !94, !87}
!108 = distinct !{!108, !59}
