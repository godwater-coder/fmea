
/**
 * 获取字典数据
 */
export function fullUrl(url) {
    if (url && url.startsWith('http')) {
        return url
    }
    return import.meta.env.VITE_APP_BASE_API + url
}