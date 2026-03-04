<template>
    <div class="app-container">
        <el-form
            :model="queryParams"
            ref="queryRef"
            :inline="true"
            v-show="showSearch"
            label-width="68px"
        >
            <el-form-item label="字段名" prop="fieldName">
                <el-input
                    v-model="queryParams.fieldName"
                    placeholder="请输入字段名"
                    clearable
                    @keyup.enter="handleQuery"
                />
            </el-form-item>

            <el-form-item label="驼峰属性" prop="prop">
                <el-input
                    v-model="queryParams.prop"
                    placeholder="请输入驼峰属性"
                    clearable
                    @keyup.enter="handleQuery"
                />
            </el-form-item>

            <el-form-item label="表名" prop="tableName">
                <el-input
                    v-model="queryParams.tableName"
                    placeholder="请输入表名"
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

        <el-row :gutter="10" class="mb8">
            <el-col :span="1.5">
                <el-button
                    type="primary"
                    plain
                    icon="Upload"
                    @click="openImportTable"
                    v-hasPermi="['sys:table:add']"
                    >导入</el-button
                >
            </el-col>
            <el-col :span="1.5">
                <el-button
                    type="success"
                    plain
                    icon="Plus"
                    @click="handleAdd"
                    v-hasPermi="['sys:table:add']"
                    >添加</el-button
                >
            </el-col>
            <el-col :span="1.5">
                <el-button
                    type="info"
                    plain
                    icon="Edit"
                    :disabled="single"
                    @click="handleUpdate"
                    v-hasPermi="['sys:table:edit']"
                    >修改</el-button
                >
            </el-col>
            <el-col :span="1.5">
                <el-button
                    type="danger"
                    plain
                    icon="Delete"
                    :disabled="multiple"
                    @click="handleDelete"
                    v-hasPermi="['sys:table:remove']"
                    >删除</el-button
                >
            </el-col>
            <el-col :span="1.5">
                <el-button
                    type="warning"
                    plain
                    icon="Download"
                    @click="handleExport"
                    v-hasPermi="['sys:table:export']"
                    >导出</el-button
                >
            </el-col>
            <right-toolbar
                v-model:showSearch="showSearch"
                @queryTable="getList"
            ></right-toolbar>
        </el-row>

        <el-table
            v-loading="loading"
            :data="tableList"
            @selection-change="handleSelectionChange"
        >
            <el-table-column type="selection" width="55" align="center" />

            <el-table-column label="字段名" align="center" prop="fieldName" />

            <el-table-column label="表名" align="center" prop="tableName" />

            <el-table-column label="宽度" align="center" prop="width" />

            <el-table-column label="字段顺序" align="center" prop="sequence" />

            <el-table-column label="对其方式" align="center" prop="align">
                <template #default="scope">
                    <dict-tag :options="field_align" :value="scope.row.align" />
                </template>
            </el-table-column>

            <el-table-column label="固定列" align="center" prop="fixed">
                <template #default="scope">
                    {{
                        scope.row.fixed == 0
                            ? 'No'
                            : scope.row.fixed == 1
                            ? 'Left'
                            : 'Right'
                    }}
                    <!-- <dict-tag
                        :options="sys_01_yes_no"
                        :value="scope.row.fixed"
                    /> -->
                </template>
            </el-table-column>

            <el-table-column label="字段标签" align="center" prop="label" />

            <el-table-column label="标签解释" align="center" prop="labelTip" />

            <el-table-column label="驼峰属性" align="center" prop="prop" />

            <el-table-column label="可见" align="center" prop="show">
                <template #default="scope">
                    <dict-tag
                        :options="sys_01_yes_no"
                        :value="scope.row.show"
                    />
                </template>
            </el-table-column>

            <el-table-column label="可排序" align="center" prop="sortable">
                <template #default="scope">
                    <dict-tag
                        :options="sys_01_yes_no"
                        :value="scope.row.sortable"
                    />
                </template>
            </el-table-column>

            <el-table-column label="超出隐藏" align="center" prop="tooltip">
                <template #default="scope">
                    <dict-tag
                        :options="sys_01_yes_no"
                        :value="scope.row.tooltip"
                    />
                </template>
            </el-table-column>

            <el-table-column
                label="更新者"
                align="center"
                prop="updateByName"
            />

            <el-table-column
                label="更新时间"
                align="center"
                width="160"
                prop="updateTime"
            />

            <el-table-column
                label="操作"
                align="center"
                width="200"
                class-name="small-padding fixed-width"
            >
                <template #default="scope">
                    <el-button
                        link
                        type="primary"
                        icon="Edit"
                        @click="handleUpdate(scope.row)"
                        v-hasPermi="['sys:table:edit']"
                        >修改</el-button
                    >
                    <el-button
                        link
                        type="primary"
                        icon="Delete"
                        @click="handleDelete(scope.row)"
                        v-hasPermi="['sys:table:remove']"
                        >删除</el-button
                    >
                </template>
            </el-table-column>
        </el-table>

        <pagination
            v-show="total > 0"
            :total="total"
            v-model:page="queryParams.pageNum"
            v-model:limit="queryParams.pageSize"
            @pagination="getList"
        />

        <!-- 添加或修改表格管理对话框 -->
        <el-dialog :title="title" v-model="open" width="800px" append-to-body>
            <el-form
                ref="tableRef"
                :model="form"
                :rules="rules"
                label-width="80px"
            >
                <el-form-item label="对其方式" prop="align">
                    <el-select
                        v-model="form.align"
                        placeholder="请选择对其方式"
                    >
                        <el-option
                            v-for="dict in field_align"
                            :key="dict.value"
                            :label="dict.label"
                            :value="dict.value"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <el-form-item label="字段名" prop="fieldName">
                    <el-input
                        v-model="form.fieldName"
                        placeholder="请输入字段名"
                    />
                </el-form-item>

                <el-form-item label="固定列" prop="fixed">
                    <el-select
                        v-model="form.fixed"
                        placeholder="请选择固定方向"
                    >
                        <el-option
                            :key="0"
                            label="不固定"
                            value="0"
                        ></el-option>
                        <el-option
                            :key="1"
                            label="左侧固定"
                            value="1"
                        ></el-option>
                        <el-option
                            :key="2"
                            label="右侧固定"
                            value="2"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <el-form-item label="字段标签" prop="label">
                    <el-input
                        v-model="form.label"
                        placeholder="请输入字段标签"
                    />
                </el-form-item>

                <el-form-item label="标签解释" prop="labelTip">
                    <el-input
                        v-model="form.labelTip"
                        placeholder="请输入字段标签解释"
                    />
                </el-form-item>

                <el-form-item label="驼峰属性" prop="prop">
                    <el-input
                        v-model="form.prop"
                        placeholder="请输入驼峰属性"
                    />
                </el-form-item>

                <el-form-item label="可见" prop="show">
                    <el-select v-model="form.show" placeholder="请选择可见">
                        <el-option
                            v-for="dict in sys_01_yes_no"
                            :key="dict.value"
                            :label="dict.label"
                            :value="dict.value"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <el-form-item label="可排序" prop="sortable">
                    <el-select
                        v-model="form.sortable"
                        placeholder="请选择可排序"
                    >
                        <el-option
                            v-for="dict in sys_01_yes_no"
                            :key="dict.value"
                            :label="dict.label"
                            :value="dict.value"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <el-form-item label="表名" prop="tableName">
                    <el-input
                        v-model="form.tableName"
                        placeholder="请输入表名"
                    />
                </el-form-item>

                <el-form-item label="超出隐藏" prop="tooltip">
                    <el-select
                        v-model="form.tooltip"
                        placeholder="请选择超出隐藏"
                    >
                        <el-option
                            v-for="dict in sys_01_yes_no"
                            :key="dict.value"
                            :label="dict.label"
                            :value="dict.value"
                        ></el-option>
                    </el-select>
                </el-form-item>

                <!-- <el-form-item label="更新者" prop="updateBy">
                    <el-input
                        v-model="form.updateBy"
                        placeholder="请输入更新者"
                    />
                </el-form-item>

                <el-form-item label="更新者" prop="updateByName">
                    <el-input
                        v-model="form.updateByName"
                        placeholder="请输入更新者"
                    />
                </el-form-item> -->

                <el-form-item label="宽度" prop="width">
                    <el-input v-model="form.width" placeholder="请输入宽度" />
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
        <import-sys-table ref="importRef" @ok="handleQuery" />
    </div>
</template>

<script setup name="Table">
import {
    listTable,
    getTable,
    delTable,
    addTable,
    updateTable
} from '@/api/system/table'

import importSysTable from './importSysTable'

const { proxy } = getCurrentInstance()

const { field_align, sys_01_yes_no } = proxy.useDict(
    'field_align',
    'sys_01_yes_no'
)

const tableList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref('')

const data = reactive({
    form: {},
    queryParams: {
        pageNum: 1,
        pageSize: 10,
        fieldName: null,
        prop: null,
        tableName: null
    },
    rules: {
        align: [
            { required: true, message: '对其方式不能为空', trigger: 'blur' }
        ],
        delFlag: [
            { required: true, message: '删除标志不能为空', trigger: 'blur' }
        ],
        fieldName: [
            { required: true, message: '字段名不能为空', trigger: 'blur' }
        ],
        fixed: [
            { required: true, message: '固定表头不能为空', trigger: 'blur' }
        ],
        label: [
            { required: true, message: '字段标签不能为空', trigger: 'blur' }
        ],
        prop: [
            { required: true, message: '驼峰属性不能为空', trigger: 'blur' }
        ],
        show: [{ required: true, message: '可见不能为空', trigger: 'blur' }],
        sortable: [
            { required: true, message: '可排序不能为空', trigger: 'blur' }
        ],
        tableName: [
            { required: true, message: '表名不能为空', trigger: 'blur' }
        ],
        tooltip: [
            { required: true, message: '超出隐藏不能为空', trigger: 'blur' }
        ],
        width: [{ required: true, message: '宽度不能为空', trigger: 'blur' }]
    }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询表格管理列表 */
function getList() {
    loading.value = true
    listTable(queryParams.value).then((response) => {
        tableList.value = response.rows
        total.value = response.total
        loading.value = false
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
        align: null,
        createTime: null,
        delFlag: null,
        fieldName: null,
        fixed: null,
        id: null,
        label: null,
        labelTip: null,
        prop: null,
        show: null,
        sortable: null,
        tableName: null,
        tooltip: null,
        updateTime: null,
        width: null
    }
    proxy.resetForm('tableRef')
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
    title.value = '添加表格管理'
}

/** 修改按钮操作 */
function handleUpdate(row) {
    reset()
    const sysTableId = row.id || ids.value
    getTable(sysTableId).then((response) => {
        form.value = response.data
        open.value = true
        title.value = '修改表格管理'
    })
}

/** 提交按钮 */
function submitForm() {
    proxy.$refs['tableRef'].validate((valid) => {
        if (valid) {
            if (form.value.id != null) {
                updateTable(form.value).then((response) => {
                    proxy.$modal.msgSuccess('修改成功')
                    open.value = false
                    getList()
                })
            } else {
                addTable(form.value).then((response) => {
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
        .confirm('是否确认删除表格管理编号为"' + _ids + '"的数据项？')
        .then(function () {
            return delTable(_ids)
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
        'sys/table/export',
        {
            ...queryParams.value
        },
        `table_${new Date().getTime()}.xlsx`
    )
}

/** 打开导入表弹窗 */
function openImportTable() {
    proxy.$refs['importRef'].show()
}

getList()
</script>