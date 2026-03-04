import request from '@/utils/request'

// 查询司机信息列表
export function listDriver(query) {
  return request({
    url: '/car/driver/list',
    method: 'get',
    params: query
  })
}

// 查询司机信息详细
export function getDriver(id) {
  return request({
    url: '/car/driver/getById/' + id,
    method: 'get'
  })
}

// 新增司机信息
export function addDriver(data) {
  return request({
    url: '/car/driver/add',
    method: 'post',
    data: data
  })
}

// 修改司机信息
export function updateDriver(data) {
  return request({
    url: '/car/driver/update',
    method: 'put',
    data: data
  })
}

// 删除司机信息
export function delDriver(id) {
  return request({
    url: '/car/driver/delete/' + id,
    method: 'delete'
  })
}

// 导入司机信息
export function importDriver(data) {
    return request({
      url: '/car/driver/import',
      method: 'post',
      data: data
    })
  }
  