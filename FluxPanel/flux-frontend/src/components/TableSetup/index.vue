<template>
    <div class="table-toolbar">
        <div class="items-center table-toolbar-left">
            <slot name="operate"></slot>
        </div>
        <div class="items-center table-toolbar-right">
            <el-tooltip effect="dark" content="表格边框" placement="top">
                <div class="table-toolbar-right-icon mr-2">
                    <el-switch v-model="stripe" @change="onStripe"></el-switch>
                </div>
            </el-tooltip>
            <el-divider direction="vertical"></el-divider>
            <el-tooltip effect="dark" content="刷新表格" placement="top">
                <div class="table-toolbar-right-icon" @click="onRefresh">
                    <el-icon><RefreshRight /></el-icon>
                </div>
            </el-tooltip>
            <el-tooltip effect="dark" content="搜索显隐" placement="top">
                <div class="table-toolbar-right-icon" @click="onSearchChange">
                    <el-icon><Search /></el-icon>
                </div>
            </el-tooltip>
            <el-tooltip
                effect="dark"
                content="表格设置"
                placement="top"
                v-if="isTable"
            >
                <div class="table-toolbar-right-icon">
                    <el-popover
                        placement="bottom-end"
                        width="380"
                        trigger="click"
                        @show="popoverShow"
                        @hide="popoverHide"
                    >
                        <div class="toolbar-inner-popover-title">
                            <div class="flex items-center justify-between">
                                <div class="setup-title">列表设置</div>
                            </div>
                        </div>
                        <template v-if="sonColumns.length > 0">
                            <div class="draggable-scroll" v-if="popoverVisible">
                                <draggable
                                    v-model="sonColumns"
                                    handle=".mover"
                                    chosen-class="chosen"
                                    force-fallback="true"
                                    group="people"
                                    animation="300"
                                    item-key="id"
                                    @update="onUpdate"
                                    @start="onDragStart"
                                >
                                    <template #item="{ element }">
                                        <div
                                            class="table-toolbar-inner-checkbox"
                                        >
                                            <div class="flexbox">
                                                <el-button
                                                    class="drag-title mover"
                                                    link
                                                    >{{
                                                        element.label
                                                    }}</el-button
                                                >
                                            </div>
                                            <el-tooltip
                                                effect="dark"
                                                content="文本超出隐藏"
                                                placement="top"
                                            >
                                                <el-checkbox
                                                    :key="element.id"
                                                    v-model="element.tooltip"
                                                    @change="onTooltip(element)"
                                                    style="margin-right: 8px"
                                                    true-value="1"
                                                    false-value="0"
                                                >
                                                </el-checkbox>
                                            </el-tooltip>
                                            <el-tooltip
                                                effect="dark"
                                                content="对齐方式"
                                                placement="top"
                                            >
                                                <el-radio-group
                                                    :key="element.id"
                                                    v-model="element.align"
                                                    size="small"
                                                    @change="onAlign(element)"
                                                >
                                                    <el-radio-button
                                                        value="left"
                                                    >
                                                        <svg-icon
                                                            class-name="size-icon"
                                                            icon-class="leftCenter"
                                                        />
                                                    </el-radio-button>
                                                    <el-radio-button
                                                        value="center"
                                                    >
                                                        <svg-icon
                                                            class-name="size-icon"
                                                            icon-class="alignCenter"
                                                        />
                                                    </el-radio-button>
                                                    <el-radio-button
                                                        value="right"
                                                    >
                                                        <svg-icon
                                                            class-name="size-icon"
                                                            icon-class="rightCenter"
                                                        />
                                                    </el-radio-button>
                                                </el-radio-group>
                                            </el-tooltip>

                                            <el-tooltip
                                                effect="dark"
                                                content="是否排序"
                                                placement="top"
                                            >
                                                <el-switch
                                                    :key="element.id"
                                                    v-model="element.sortable"
                                                    active-value="1"
                                                    inactive-value="0"
                                                    @change="onSwitch(element)"
                                                >
                                                </el-switch>
                                            </el-tooltip>
                                            <el-tooltip
                                                effect="dark"
                                                content="显示隐藏"
                                                placement="top"
                                            >
                                                <el-switch
                                                    :key="element.id"
                                                    v-model="element.show"
                                                    active-value="1"
                                                    inactive-value="0"
                                                    @change="onSwitch(element)"
                                                >
                                                </el-switch>
                                            </el-tooltip>

                                            <el-tooltip
                                                effect="dark"
                                                content="固定列"
                                                placement="top"
                                            >
                                                <el-radio-group
                                                    v-model="element.fixed"
                                                    size="small"
                                                    @change="onSwitch(element)"
                                                >
                                                    <el-radio-button value="1">
                                                        <svg-icon
                                                            class-name="size-icon"
                                                            icon-class="leftCenter"
                                                    /></el-radio-button>
                                                    <el-radio-button value="0"
                                                        ><svg-icon
                                                            class-name="size-icon"
                                                            icon-class="alignCenter"
                                                    /></el-radio-button>
                                                    <el-radio-button value="2">
                                                        <svg-icon
                                                            class-name="size-icon"
                                                            icon-class="rightCenter"
                                                    /></el-radio-button> </el-radio-group
                                            ></el-tooltip>
                                        </div>
                                    </template>
                                    <!-- <transition-group>
                                        <div
                                            class="table-toolbar-inner-checkbox"
                                            v-for="item in sonColumns"
                                            :key="item.id"
                                        ></div>
                                    </transition-group> -->
                                </draggable>
                            </div>
                        </template>
                        <template v-else>
                            <el-empty description="暂无数据"></el-empty>
                        </template>
                        <template #reference>
                            <el-icon><Setting /></el-icon>
                        </template>
                    </el-popover>
                </div>
            </el-tooltip>
            <el-tooltip effect="dark" content="不可设置" placement="top" v-else>
                <div class="table-toolbar-right-icon">
                    <el-icon><Setting /></el-icon>
                </div>
            </el-tooltip>
            <el-tooltip effect="dark" content="全屏" placement="top">
                <div class="table-toolbar-right-icon" @click="click">
                    <el-icon><FullScreen /></el-icon>
                </div>
            </el-tooltip>
        </div>
    </div>
</template>

<script>
import { ref, watch } from 'vue'
import { updateTable, modifySort } from '@/api/system/table'
import draggable from 'vuedraggable'
import screenfull from 'screenfull'

export default {
    name: 'TableSetup',
    props: ['columns', 'isTable'],
    components: {
        draggable
    },
    setup(props, { emit }) {
        const stripe = ref(true)
        const sonColumns = ref([])
        const backupColumns = ref([])
        const popoverVisible = ref(false)

        watch(
            () => props.columns,
            (newVal) => {
                sonColumns.value = newVal
            },
            { immediate: true, deep: true }
        )

        const onStripe = () => {
            emit('onStripe', stripe.value)
        }

        const onRefresh = () => {
            emit('onRefresh')
        }

        const onSearchChange = () => {
            emit('onSearchChange')
        }

        const onDragStart = () => {
            backupColumns.value = [...sonColumns.value]
        }

        const onUpdate = () => {
            let header = []
            for (var i = 0; i < sonColumns.value.length; i++) {
                header.push(sonColumns.value[i].id)
            }
            modifySort({
                ids: header
            })
                .then((res) => {
                    if (res.code == 200) {
                        emit('onChange', sonColumns.value)
                    } else {
                        console.warn(res.msg)
                    }
                })
                .catch((error) => {
                    sonColumns.value = [...backupColumns.value]
                })
        }

        const onAlign = (item) => {
            updateColumnItem(item)
        }

        const onSwitch = (item) => {
            updateColumnItem(item)
        }

        const onTooltip = (item) => {
            updateColumnItem(item)
        }

        const tableWidth = (item) => {
            updateColumnItem(item)
        }

        const updateColumnItem = (row) => {
            updateTable({
                id: row.id,
                prop: row.prop,
                label: row.label,
                sortable: row.sortable,
                width: row.width,
                fixed: row.fixed,
                align: row.align,
                show: row.show,
                tooltip: row.tooltip
            })
                .then((res) => {
                    if (res.code == 200) {
                        emit('onChange', sonColumns.value)
                    } else {
                        console.warn('修改失败')
                    }
                })
                .catch((error) => {})
        }

        const click = () => {
            emit('onfullTable')
        }

        const onFull = (el) => {
            if (!screenfull.enabled) {
                console.warn('您的浏览器不支持！')
                return false
            }
            screenfull.toggle(el)
        }

        const popoverShow = () => {
            popoverVisible.value = true
        }

        const popoverHide = () => {
            popoverVisible.value = false
        }

        return {
            stripe,
            sonColumns,
            backupColumns,
            popoverVisible,
            onStripe,
            onRefresh,
            onSearchChange,
            onUpdate,
            onDragStart,
            onAlign,
            onSwitch,
            onTooltip,
            tableWidth,
            click,
            onFull,
            popoverShow,
            popoverHide
        }
    }
}
</script>

<style scoped>
.table-toolbar {
    display: flex;
    justify-content: space-between;
    overflow: auto;
}

.table-toolbar-left {
    display: flex;
    justify-content: flex-start;
    flex: 2;
    white-space: nowrap;
}

.table-toolbar-right {
    display: flex;
    justify-content: flex-end;
    flex: 2;
    white-space: nowrap;
}

.table-toolbar-right-icon {
    margin-left: 8px;
    cursor: pointer;
}

.table-toolbar-right-icon i {
    font-size: 16px;
}

.table-toolbar-right-icon svg {
    font-size: 14px;
}

.table-toolbar-inner-checkbox {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 5px;
    border-radius: 3px;
}

.table-toolbar-inner-checkbox:hover {
    background-color: #e6f7ff;
}

.table-toolbar-inner-checkbox .drag-title {
    width: 80px;
    font-size: 12px;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: move;
}

.setup-title {
    padding: 3px 0;
}

.flexbox {
    display: flex;
    align-items: center;
}

.screenfull-svg {
    display: inline-block;
    cursor: pointer;
    fill: #5a5e66;
    width: 20px;
    height: 20px;
    vertical-align: 10px;
}

.steup-title {
    font-weight: 600;
    color: #221f25;
}

.draggable-scroll {
    max-height: 500px;
    overflow-y: auto;
}
.items-center {
    align-items: center !important;
}

:deep(
        .table-toolbar-inner-checkbox
            .el-radio-button--small
            .el-radio-button__inner
    ) {
    padding: 4px 6px;
    font-size: 12px;
}
</style>