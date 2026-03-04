<template>
    <div class="app-container">
        <el-form
            ref="formRef"
            :model="formData"
            :rules="rules"
            size="default"
            label-width="100px"
        >
            <el-form-item label="手机号" prop="mobile">
                <el-input
                    v-model="formData.mobile"
                    placeholder="请输入手机号"
                    :maxlength="11"
                    show-word-limit
                    clearable
                    prefix-icon="Cellphone"
                    :style="{ width: '100%' }"
                ></el-input>
            </el-form-item>
            <el-form-item label="姓名" prop="name">
                <el-input
                    v-model="formData.name"
                    type="text"
                    placeholder="请输入姓名"
                    clearable
                    :style="{ width: '100%' }"
                ></el-input>
            </el-form-item>
            <el-form-item label="年龄" prop="age">
                <el-input
                    v-model="formData.age"
                    type="text"
                    placeholder="请输入年龄"
                    clearable
                    :style="{ width: '100%' }"
                ></el-input>
            </el-form-item>
            <el-form-item label="期望薪资" prop="salary">
                <el-input
                    v-model="formData.salary"
                    type="text"
                    placeholder="请输入期望薪资"
                    clearable
                    :style="{ width: '100%' }"
                ></el-input>
            </el-form-item>
            <el-form-item label="入职时间" prop="joinDate">
                <el-date-picker
                    v-model="formData.joinDate"
                    format="YYYY-MM-DD"
                    value-format="YYYY-MM-DD"
                    :style="{ width: '100%' }"
                    placeholder="请选择入职时间"
                    clearable
                ></el-date-picker>
            </el-form-item>
            <el-form-item label="下拉选择" prop="field101">
                <el-select
                    v-model="formData.field101"
                    placeholder="请选择下拉选择"
                    clearable
                    :style="{ width: '100%' }"
                >
                    <el-option
                        v-for="(item, index) in field101Options"
                        :key="index"
                        :label="item.label"
                        :value="item.value"
                        :disabled="item.disabled"
                    ></el-option>
                </el-select>
            </el-form-item>
            <el-form-item>
                <el-button type="primary" @click="submitForm">提交</el-button>
                <el-button @click="resetForm">重置</el-button>
            </el-form-item>
        </el-form>
    </div>
</template>
<script setup>
import { addForm_data } from '@/api/system/form_data'
const { proxy } = getCurrentInstance()
const formRef = ref()
const data = reactive({
    formData: {
        mobile: '',
        name: undefined,
        age: undefined,
        salary: undefined,
        joinDate: null,
        field101: undefined
    },
    rules: {
        mobile: [
            {
                required: true,
                message: '请输入手机号',
                trigger: 'blur'
            },
            {
                pattern: new RegExp(/^1(3|4|5|7|8|9)\d{9}$/),
                message: '手机号格式错误',
                trigger: 'blur'
            }
        ],
        name: [
            {
                required: true,
                message: '请输入姓名',
                trigger: 'blur'
            }
        ],
        age: [
            {
                required: true,
                message: '请输入年龄',
                trigger: 'blur'
            }
        ],
        salary: [
            {
                required: true,
                message: '请输入期望薪资',
                trigger: 'blur'
            }
        ],
        joinDate: [
            {
                required: true,
                message: '请选择入职时间',
                trigger: 'change'
            }
        ],
        field101: [
            {
                required: true,
                message: '请选择下拉选择',
                trigger: 'change'
            }
        ]
    }
})
const { formData, rules } = toRefs(data)
const field101Options = ref([
    {
        label: '选项一',
        value: 1
    },
    {
        label: '选项二',
        value: 2
    }
])
/**
 * @name: 表单提交
 * @description: 表单提交方法
 * @return {*}
 */
function submitForm() {
    formRef.value.validate((valid) => {
        if (!valid) return
        // 提交表单
        let tempFormData = JSON.stringify(formData.value)
        let params = {
            formName: '求职意向调查',
            formData: tempFormData
        }
        addForm_data(params).then((response) => {
            proxy.$modal.msgSuccess('新增成功')
            resetForm()
        })
    })
}
/**
 * @name: 表单重置
 * @description: 表单重置方法
 * @return {*}
 */
function resetForm() {
    formRef.value.resetFields()
}
</script>
<style>
</style>
