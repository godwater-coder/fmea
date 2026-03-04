<template>
    <el-dialog
        v-model="visible"
        title="导入数据"
        width="600px"
        @close="handleClose"
    >
        <div>
            <el-upload
                v-if="showUpload"
                class="upload-box"
                :action="uploadImgUrl"
                :data="{ tableName }"
                :on-success="handleSuccess"
                :before-upload="beforeUpload"
                :headers="headers"
                accept=".xls,.xlsx"
                drag
            >
                <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                <div class="el-upload__text">拖拽或 <em>点击上传</em></div>
                <template #tip>
                    <div class="el-upload__tip">
                        仅支持 Excel 文件 (.xls, .xlsx)
                    </div>
                </template>
            </el-upload>

            <el-form v-else :model="targetForm" label-width="80px" ref="form">
                <el-form-item label="选择sheet">
                    <el-col :span="1">
                        <el-icon><Files /></el-icon>
                    </el-col>
                    <el-col :span="23">
                        <el-select
                            v-model="currentSheet"
                            placeholder="请选择sheet"
                            @change="handleSheetChange"
                            ><el-option
                                v-for="sheet in sheetNames"
                                :key="sheet"
                                :label="sheet"
                                :value="sheet"
                            />
                        </el-select>
                    </el-col>
                </el-form-item>
                <el-divider>
                    <el-text class="mx-1" size="small" type="danger"
                        >标签为数据表字段，选择列为Excel表字段</el-text
                    >
                </el-divider>

                <el-form-item
                    v-for="(column, index) in tableColumns"
                    :key="column.name"
                    :label="
                        column.columnComment
                            ? column.columnComment
                            : column.columnName
                    "
                >
                    <el-row style="flex: 1; width: 100%">
                        <el-col :span="1">
                            <el-checkbox
                                v-model="targetForm[index]['selected']"
                                :disabled="targetForm[index].isRequired == '1'"
                            ></el-checkbox>
                        </el-col>
                        <el-col :span="15">
                            <el-select
                                v-model="targetForm[index]['excelColumn']"
                                placeholder="请选择列绑定关系"
                                clearable
                            >
                                <el-option
                                    v-for="excelCol in excelColumns"
                                    :key="excelCol"
                                    :label="excelCol"
                                    :value="excelCol"
                                />
                            </el-select>
                        </el-col>
                        <el-col :span="1"> </el-col>
                        <el-col :span="7">
                            <el-input
                                v-model="targetForm[index]['defaultValue']"
                                placeholder="默认值"
                            ></el-input>
                        </el-col>
                    </el-row>
                </el-form-item>
                <el-form-item>
                    <el-button type="primary" @click="handleSubmit">
                        确定
                    </el-button>
                    <el-button @click="handleClose">取消</el-button>
                </el-form-item>
            </el-form>
        </div>
    </el-dialog>
</template>
  
  <script setup>
import { ref, defineProps, defineEmits } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElLoading, ElMessage } from 'element-plus'
import { getToken } from '@/utils/auth'
import { tr } from 'element-plus/es/locales.mjs'

const targetForm = ref([]) // 表单数据
const filename = ref('') // 上传的文件名

const uploadImgUrl = ref(
    import.meta.env.VITE_APP_BASE_API + '/import/uploadExcel'
) // 上传的图片服务器地址
const headers = ref({ Authorization: 'Bearer ' + getToken() })
const props = defineProps({
    tableName: {
        type: String,
        required: true // 确保 tableName 必传
    }
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = ref(true)
const showUpload = ref(true)
const currentSheet = ref('') //当前选中的 sheetconst
const sheetNames = ref([]) // Excel sheet 列表
const sheetExcelColumns = ref() // Excel 表头
const tableColumns = ref([]) // 表格列
const excelColumns = ref([]) // Excel 选择的表头

const handleClose = () => {
    emit('update:modelValue', false) // 关闭 dialog
}

const beforeUpload = (file) => {
    const isExcel =
        file.type === 'application/vnd.ms-excel' ||
        file.type ===
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if (!isExcel) {
        ElMessage.error('只能上传 Excel 文件！')
        return false
    }
    return true
}

const handleSheetChange = async () => {
    sheetExcelColumns.value.forEach((item) => {
        if (item.sheetName === currentSheet.value) {
            excelColumns.value = item.excelColumns || []
            //更新 targetForm 中的 excelColumn
            targetForm.value.forEach((formItem, index) => {
                const matchingExcelCol = excelColumns.value?.find(
                    (excelCol) =>
                        excelCol.toLowerCase().trim() ===
                        tableColumns.value[index].columnComment
                            .toLowerCase()
                            .trim()
                )
                formItem.excelColumn = matchingExcelCol || ''
            })
        }
    })
}

function handleSubmit() {
    const loading = ElLoading.service({
        text: '导入数据中...',
        background: 'rgba(0,,0,0.7)'
    })
    for (const item in targetForm.value) {
        if (
            item['excelColumn'] === '' &&
            item['defaultValue'] === '' &&
            item['selected']
        ) {
            ElMessage.error('请为勾选的字段选择绑定关系, 或填写默认值')
            return
        }
    }
    emit('success', currentSheet.value, targetForm.value, filename.value)
    console.log(targetForm.value)
    loading.close()
}

const handleSuccess = (response) => {
    let result = response
    if (result.code === 200) {
        sheetExcelColumns.value = result.data.sheetExcelColumns
        sheetNames.value = result.data.sheetNames
        currentSheet.value = result.data.currentSheet
        excelColumns.value = result.data.excelColumns
        tableColumns.value = result.data.tableColumns
        filename.value = result.data.filename
        targetForm.value = []
        tableColumns.value.forEach((column) => {
            targetForm.value.push({
                baseColumn: column.columnName,
                excelColumn: '',
                defaultValue: '',
                isRequired: column.isRequired,
                selected: true
            })
        })
        showUpload.value = false
    } else {
        ElMessage.error(result.msg)
    }
}
</script>
  
  <style scoped>
.upload-box {
    width: 100%;
    text-align: center;
}
</style>
  