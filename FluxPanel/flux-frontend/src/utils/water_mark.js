import useUserStore from '@/store/modules/user'
import { watch } from 'vue'


export function addWatermark() {

 
    const userStore = useUserStore()
    console.log(userStore)
    watch(
        () => userStore.name,
        (newName) => {
            console.log('userStore.name updated:', newName)
            // You can add logic here to update the watermark dynamically if needed
            const target_mark = userStore.name ? userStore.name: "Flux Panel"

            const existing = document.getElementById('my-watermark')
            if (existing) {
                existing.remove()
            }
            const watermark = document.createElement('div')
            watermark.id = 'my-watermark'
            watermark.className = 'global-watermark'
            document.body.appendChild(watermark)

            const canvas = document.createElement('canvas')
            canvas.width = 200
            canvas.height = 150
            const ctx = canvas.getContext('2d')
            ctx.clearRect(0, 0, canvas.width, canvas.height)
            ctx.save() // 保存当前状态（用于后面恢复）
            ctx.rotate((-20 * Math.PI) / 180)
            ctx.font = '16px Arial'
            ctx.fillStyle = 'rgba(180, 180, 180, 0.3)'
            ctx.textAlign = 'left'
            ctx.textBaseline = 'middle'
            ctx.fillText(target_mark, 10, 70)
            ctx.restore() // 恢复到未旋转状态，防止后续绘图出错

            watermark.style.position = 'fixed'
            watermark.style.top = '0'
            watermark.style.left = '0'
            watermark.style.width = '100%'
            watermark.style.height = '100%'
            watermark.style.backgroundImage = `url(${canvas.toDataURL()})`
            watermark.style.pointerEvents = 'none'
            watermark.style.zIndex = '9999'
        },
        { immediate: true }
    )
}