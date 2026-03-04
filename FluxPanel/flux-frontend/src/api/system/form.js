import request from '@/utils/request'

// 查询系统表单列表
export function listForm(query) {
  return request({
    url: '/sys/form/list',
    method: 'get',
    params: query
  })
}

// 查询系统表单详细
export function getForm(id) {
  return request({
    url: '/sys/form/getById/' + id,
    method: 'get'
  })
}

// 新增系统表单
export function addForm(data) {
  return request({
    url: '/sys/form/add',
    method: 'post',
    data: data
  })
}

// 修改系统表单
export function updateForm(data) {
  return request({
    url: '/sys/form/update',
    method: 'put',
    data: data
  })
}

// 删除系统表单
export function delForm(id) {
  return request({
    url: '/sys/form/delete/' + id,
    method: 'delete'
  })
}