<!-- tablePlus:二次封装table -->
<template>
    <el-table
        header-cell-class-name="tableHeader"
        stripe
        v-loading="loading"
        :data="sonTableData"
        :max-height="tableHeight"
        :border="stripe"
        @header-dragend="headerDragend"
        @selection-change="handleSelectionChange"
        highlight-current-row
        class="mytable"
    >
        <el-table-column type="selection" width="55" align="center" />
        <template v-for="(item, index) in sonColumns">
            <el-table-column
                v-if="item.show == 1"
                :key="index"
                :prop="item.prop"
                :align="item.align"
                :label="item.label"
                :sortable="item.sortable != 0"
                :width="item.width"
                :fixed="parseFixed(item.fixed)"
                :show-overflow-tooltip="item.tooltip != 0"
            >
                <template #default="scope" v-if="$slots[item.prop]">
                    <slot :name="item.prop" v-bind="scope"></slot>
                </template>
            </el-table-column>
        </template>
    </el-table>
</template>

<script>
import { ta } from 'element-plus/es/locales.mjs'
import { ref, watch } from 'vue'

export default {
    name: 'AutoTable',
    props: ['tableData', 'columns', 'loading', 'stripe', 'tableHeight'],
    components: {},
    setup(props, { emit }) {
        const stripe = ref(true)
        const sonColumns = ref([])
        const sonTableData = ref([])
        const loading = ref(false)
        const tableHeight = ref(500)

        watch(
            () => props.columns,
            (newVal) => {
                sonColumns.value = newVal
            },
            { immediate: true, deep: true }
        )
        watch(
            () => props.tableData,
            (newVal) => {
                sonTableData.value = newVal
            },
            { immediate: true, deep: true }
        )

        watch(
            () => props.stripe,
            (newVal) => {
                stripe.value = newVal
            },
            { immediate: true, deep: true }
        )

        watch(
            () => props.tableHeight,
            (newVal) => {
                tableHeight.value = newVal
            },
            { immediate: true, deep: true }
        )

        const headerDragend = (newWidth, oldWidth, column, event) => {
            for (var i = 0; i < sonColumns.value.length; i++) {
                if (sonColumns.value[i].prop === column.property) {
                    sonColumns.value[i].width = parseInt(newWidth)
                    emit('onColumnWidthChange', sonColumns.value[i])
                }
            }
        }

        const handleSelectionChange = (selection) => {
            emit('onSelectionChange', selection)
        }

        const parseFixed = (value) => {
            if (value === '0') return false
            if (value === '1') return 'left' // 如果需要的话
            if (value === '2') return 'right'
            return value // 'left' 或 'right'
        }

        return {
            stripe,
            sonColumns,
            loading,
            sonTableData,
            tableHeight,
            parseFixed,
            headerDragend,
            handleSelectionChange
        }
    }
}
</script>


<style scoped>
.mytable {
    margin-top: 10px;
}

.disabled_class {
    color: #fff;
    background-color: #fab6b6;
    border-color: #fab6b6;
}

.disabled_class:hover {
    cursor: not-allowed;
}
</style>