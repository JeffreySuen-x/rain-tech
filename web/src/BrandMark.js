import { defineComponent, h } from 'vue'
import { brandLogoUrl } from './brand.js'
export default defineComponent({ name: 'BrandMark', setup() { return () => h('img', { src: brandLogoUrl, alt: '', class: 'shuyu-brand-mark', draggable: false }) } })
