import request from '@/utils/request'

// 查询表单数据列表
export function listForm_data(query) {
  return request({
    url: '/sys/form_data/list',
    method: 'get',
    params: query
  })
}

// 查询表单数据详细
export function getForm_data(id) {
  return request({
    url: '/sys/form_data/getById/' + id,
    method: 'get'
  })
}

// 新增表单数据
export function addForm_data(data) {
  return request({
    url: '/sys/form_data/add',
    method: 'post',
    data: data
  })
}

// 修改表单数据
export function updateForm_data(data) {
  return request({
    url: '/sys/form_data/update',
    method: 'put',
    data: data
  })
}

// 删除表单数据
export function delForm_data(id) {
  return request({
    url: '/sys/form_data/delete/' + id,
    method: 'delete'
  })
}