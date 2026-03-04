import request from '@/utils/request'



  // 更新表列顺序
export function modifySort(data) {
    return request({
      url: '/sys/table/column/sort',
      method: 'post',
      data: data
    })
}
  
// 导入表
export function importSysTable(data) {
    return request({
      url: '/sys/table/import',
      method: 'post',
      params: data
    })
}

// 查询表格管理列表
export function listTable(query) {
    return request({
      url: '/sys/table/list',
      method: 'get',
      params: query
    })
}
  
// 查询表格管理列表
export function listAllTable(query) {
    return request({
      url: '/sys/table/listAll',
      method: 'get',
      params: query
    })
  }
  
  // 查询表格管理详细
  export function getTable(id) {
    return request({
      url: '/sys/table/getById/' + id,
      method: 'get'
    })
  }
  
  // 新增表格管理
  export function addTable(data) {
    return request({
      url: '/sys/table/add',
      method: 'post',
      data: data
    })
  }
  
  // 修改表格管理
  export function updateTable(data) {
    return request({
      url: '/sys/table/update',
      method: 'put',
      data: data
    })
  }
  
  // 删除表格管理
  export function delTable(id) {
    return request({
      url: '/sys/table/delete/' + id,
      method: 'delete'
    })
  }
  
// 查询db数据库列表
export function listDbTable(query) {
  return request({
    url: '/sys/table/db/list',
    method: 'get',
    params: query
  })
}