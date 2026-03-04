<template>
    <div class="app-container">
        <el-form
            :model="queryParams"
            ref="queryRef"
            :inline="true"
            v-show="showSearch"
            label-width="68px"
        >
            <el-form-item label="性别" prop="gender">
                <el-select
                    v-model="queryParams.gender"
                    placeholder="请选择性别"
                    style="width: 180px"
                    clearable
                >
                    <el-option
                        v-for="dict in sys_user_sex"
                        :key="dict.value"
                        :label="dict.label"
                        :value="dict.value"
                    />
                </el-select>
            </el-form-item>

            <el-form-item label="姓名" prop="name">
                <el-input
                    v-model="queryParams.name"
                    placeholder="请输入姓名"
                    clearable
                    @keyup.enter="handleQuery"
                />
            </el-form-item>

            <el-form-item label="联系电话" prop="phoneNumber">
                <el-input
                    v-model="queryParams.phoneNumber"
                    placeholder="请输入联系电话"
                    clearable
                    @keyup.enter="handleQuery"
                />
            </el-form-item>
            <el-form-item>
                <el-button type="primary" icon="Search" @click="handleQuery"
                    >搜索</el-button
                >
                <el-button icon="Refresh" @click="resetQuery">重置</el-button>
            </el-form-item>
        </el-form>

        <el-card class="base-table" ref="fullTable">
            <TableSetup
                ref="tSetup"
                @onStripe="onStripe"
                @onRefresh="onRefresh"
                @onChange="onChange"
                @onfullTable="onfullTable"
                @onSearchChange="onSearchChange"
                :columns="columns"
                :isTable="isTable"
            >
                <template v-slot:operate>
                    <el-button
                        type="primary"
                        plain
                        icon="Plus"
                        @click="handleAdd"
                        v-hasPermi="['student:info:add']"
                        >新增</el-button
                    >
                    <el-button
                        type="success"
                        plain
                        icon="Edit"
                        :disabled="single"
                        @click="handleUpdate"
                        v-hasPermi="['student:info:edit']"
                        >修改</el-button
                    >
                    <el-button
                        type="danger"
                        plain
                        icon="Delete"
                        :disabled="multiple"
                        @click="handleDelete"
                        v-hasPermi="['student:info:remove']"
                        >删除</el-button
                    >
                    <el-button
                        type="primary"
                        plain
                        icon="Upload"
                        @click="handleImport"
                        v-hasPermi="['student:info:import']"
                        >导入</el-button
                    >
                    <el-button
                        type="warning"
                        plain
                        icon="Download"
                        @click="handleExport"
                        v-hasPermi="['student:info:export']"
                        >导出</el-button
                    >
                </template>
            </TableSetup>
            <auto-table
                ref="multipleTable"
                class="mytable"
                :tableData="infoList"
                :columns="columns"
                :loading="loading"
                :stripe="stripe"
                :tableHeight="tableHeight"
                @onColumnWidthChange="onColumnWidthChange"
                @onSelectionChange="handleSelectionChange"
            >
                <template #dateOfBirth="{ row }">
                    <span>{{ parseTime(row.dateOfBirth, '{y}-{m}-{d}') }}</span>
                </template>

                <template #gender="{ row }">
                    <dict-tag :options="sys_user_sex" :value="row.gender" />
                </template>

                <template #updateTime="{ row }">
                    <span>{{ parseTime(row.updateTime, '{y}-{m}-{d}') }}</span>
                </template>
                <template #operate="{ row }">
                    <el-button
                        link
                        type="primary"
                        icon="Edit"
                        @click="handleUpdate(row)"
                        v-hasPermi="['student:info:edit']"
                        >修改</el-button
                    >
                    <el-button
                        link
                        type="primary"
                        icon="Delete"
                        @click="handleDelete(row)"
                        v-hasPermi="['student:info:remove']"
                        >删除</el-button
                    >
                </template>
            </auto-table>
            <div class="table-pagination">
                <pagination
                    v-show="total > 0"
                    :total="total"
                    v-model:page="queryParams.pageNum"
                    v-model:limit="queryParams.pageSize"
                    @pagination="getList"
                />
            </div>
        </el-card>

        <!-- 添加或修改学生信息表对话框 -->
        <el-dialog :title="title" v-model="open" width="800px" append-to-body>
            <el-form
                ref="infoRef"
                :model="form"
                :rules="rules"
                label-width="80px"
            >
                <el-form-item label="班级" prop="className">
                    <el-input
                        v-model="form.className"
                        placeholder="请输入班级"
                    />
                </el-form-item>

                <el-form-item label="出生日期" prop="dateOfBirth">
                    <el-date-picker
                        clearable
                        v-model="form.dateOfBirth"
                        type="date"
                        value-format="YYYY-MM-DD"
                        placeholder="请选择出生日期"
                    >
                    </el-date-picker>
                </el-form-item>

                <el-form-item label="电子邮箱" prop="email">
                    <el-input
                        v-model="form.email"
                        placeholder="请输入电子邮箱"
                    />
                </el-form-item>

                <el-form-item label="性别" prop="gender">
                    <el-select v-model="form.gender" placeholder="请选择性别">
                        <el-option
                            v-for="dict in sys_user_sex"
                            :key="dict.value"
                            :label="dict.label"
                            :value="dict.value"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <el-form-item label="专业" prop="major">
                    <el-input v-model="form.major" placeholder="请输入专业" />
                </el-form-item>

                <el-form-item label="姓名" prop="name">
                    <el-input v-model="form.name" placeholder="请输入姓名" />
                </el-form-item>

                <el-form-item label="联系电话" prop="phoneNumber">
                    <el-input
                        v-model="form.phoneNumber"
                        placeholder="请输入联系电话"
                    />
                </el-form-item>
            </el-form>
            <template #footer>
                <div class="dialog-footer">
                    <el-button type="primary" @click="submitForm"
                        >确 定</el-button
                    >
                    <el-button @click="cancel">取 消</el-button>
                </div>
            </template>
        </el-dialog>
        <!-- 导入数据对话框 -->
        <ImportData
            v-if="openImport"
            v-model="openImport"
            tableName="student_info"
            @success="handleImportSuccess"
        />
    </div>
</template>

<script setup name="StudentInfo">
import {
    listInfo,
    getInfo,
    delInfo,
    addInfo,
    updateInfo,
    importInfo
} from '@/api/student/info'
import { listAllTable } from '@/api/system/table'
import TableSetup from '@/components/TableSetup'
import AutoTable from '@/components/AutoTable'
import ImportData from '@/components/ImportData'
const { proxy } = getCurrentInstance()
const { sys_user_sex } = proxy.useDict('sys_user_sex')

const infoList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref('')

const columns = ref([])
const stripe = ref(true)
const isTable = ref(true)
const tableHeight = ref(500)
const fullScreen = ref(false)
const openImport = ref(false)

const data = reactive({
    form: {},
    queryParams: {
        pageNum: 1,
        pageSize: 10,
        gender: null,
        name: null,
        phoneNumber: null
    },
    rules: {
        createBy: [
            { required: true, message: '创建者不能为空', trigger: 'blur' }
        ],
        deptId: [
            { required: true, message: '部门id不能为空', trigger: 'blur' }
        ],
        gender: [
            { required: true, message: '性别不能为空', trigger: 'change' }
        ],
        name: [{ required: true, message: '姓名不能为空', trigger: 'blur' }]
    }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询学生信息表列表 */
function getList() {
    loading.value = true
    listInfo(queryParams.value).then((response) => {
        infoList.value = response.rows
        total.value = response.total
        loading.value = false
    })
}

function getColumns() {
    listAllTable({ tableName: 'student_info' })
        .then((response) => {
            columns.value = response.data
        })
        .then(() => {
            getList()
        })
}

// 取消按钮
function cancel() {
    open.value = false
    reset()
}

// 表单重置
function reset() {
    form.value = {
        className: null,
        createBy: null,
        createTime: null,
        dateOfBirth: null,
        delFlag: null,
        deptId: null,
        email: null,
        gender: null,
        id: null,
        major: null,
        name: null,
        phoneNumber: null,
        updateTime: null
    }
    proxy.resetForm('infoRef')
}

/** 搜索按钮操作 */
function handleQuery() {
    queryParams.value.pageNum = 1
    getList()
}

/** 重置按钮操作 */
function resetQuery() {
    proxy.resetForm('queryRef')
    handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
    ids.value = selection.map((item) => item.id)
    single.value = selection.length != 1
    multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
    reset()
    open.value = true
    title.value = '添加学生信息表'
}

/** 新增按钮操作 */
function handleImport() {
    openImport.value = true
}

/** 修改按钮操作 */
function handleUpdate(row) {
    reset()
    const studentInfoId = row.id || ids.value
    getInfo(studentInfoId).then((response) => {
        form.value = response.data
        open.value = true
        title.value = '修改学生信息表'
    })
}

/** 提交按钮 */
function submitForm() {
    proxy.$refs['infoRef'].validate((valid) => {
        if (valid) {
            if (form.value.id != null) {
                updateInfo(form.value).then((response) => {
                    proxy.$modal.msgSuccess('修改成功')
                    open.value = false
                    getList()
                })
            } else {
                addInfo(form.value).then((response) => {
                    proxy.$modal.msgSuccess('新增成功')
                    open.value = false
                    getList()
                })
            }
        }
    })
}

/** 删除按钮操作 */
function handleDelete(row) {
    const _ids = row.id || ids.value
    proxy.$modal
        .confirm('是否确认删除学生信息表编号为"' + _ids + '"的数据项？')
        .then(function () {
            return delInfo(_ids)
        })
        .then(() => {
            getList()
            proxy.$modal.msgSuccess('删除成功')
        })
        .catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
    proxy.download(
        'student/info/export',
        {
            ...queryParams.value
        },
        `info_${new Date().getTime()}.xlsx`
    )
}

//表格全屏
function onfullTable() {
    proxy.$refs.tSetup.onFull(proxy.$refs.fullTable.$el)
    fullScreen.value = !fullScreen.value
    updateTableHeight()
}
//表格刷新
function onRefresh() {
    getList()
}
//搜索框显示隐藏
function onSearchChange() {
    showSearch.value = !showSearch.value
}

function onStripe(val) {
    stripe.value = val
}
//改变表头数据
function onChange(val) {
    columns.value = val
}

//改变表格宽度
function onColumnWidthChange(column) {
    proxy.$refs.tSetup.tableWidth(column)
}

//更新表格高度
function updateTableHeight() {
    if (
        proxy.$refs.tSetup &&
        proxy.$refs.queryRef &&
        document.querySelector('.table-pagination')
    ) {
        if (fullScreen.value) {
            tableHeight.value = window.innerHeight - 145
        } else {
            tableHeight.value =
                window.innerHeight -
                proxy.$refs.tSetup.$el.clientHeight -
                proxy.$refs.queryRef.$el.clientHeight -
                document.querySelector('.table-pagination').clientHeight -
                220
        }
    }
}
//导入成功
function handleImportSuccess(sheetName, filedInfo, fileName) {
    let data = {
        tableName: 'student_info',
        filedInfo: filedInfo,
        fileName: fileName,
        sheetName: sheetName
    }
    importInfo(data).then(() => {
        proxy.$modal.msgSuccess('导入成功')
        openImport.value = false
        getList()
    })
    getList()
}

onMounted(() => {
    updateTableHeight() // 初始化计算高度
    window.addEventListener('resize', updateTableHeight) // 监听窗口大小变化
})

onUnmounted(() => {
    window.removeEventListener('resize', updateTableHeight) // 销毁监听
})

getColumns()
</script>