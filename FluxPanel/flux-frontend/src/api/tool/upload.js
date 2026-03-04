import request from '@/utils/request'

// 用户头像上传
export function commonUpload(data) {
  return request({
    url: '/common/upload',
    method: 'post',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: data
  })
}