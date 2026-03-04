import request from '@/utils/request'

// 查询学生信息表列表
export function listInfo(query) {
  return request({
    url: '/student/info/list',
    method: 'get',
    params: query
  })
}

// 查询学生信息表详细
export function getInfo(id) {
  return request({
    url: '/student/info/getById/' + id,
    method: 'get'
  })
}

// 新增学生信息表
export function addInfo(data) {
  return request({
    url: '/student/info/add',
    method: 'post',
    data: data
  })
}

// 修改学生信息表
export function updateInfo(data) {
  return request({
    url: '/student/info/update',
    method: 'put',
    data: data
  })
}

// 删除学生信息表
export function delInfo(id) {
  return request({
    url: '/student/info/delete/' + id,
    method: 'delete'
  })
}

// 导入学生信息表
export function importInfo(data) {
    return request({
      url: '/student/info/import',
      method: 'post',
      data: data
    })
}