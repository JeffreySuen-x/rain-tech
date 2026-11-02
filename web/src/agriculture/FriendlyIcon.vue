<script setup>
defineProps({name:String})
const cells={calendar:0,weather:1,rain:2,leaf:6,seed:5,folder:8,camera:7,book:7,temperature:3,water:4,robot:2}
const fallback={calendar:'📅',weather:'🌤️',leaf:'🍃',seed:'🌱',folder:'📁',camera:'📷',temperature:'🌡️',water:'💧',robot:'🤖'}
</script>
<template><span class="friendly-icon" aria-hidden="true" :style="{'--icon-x':`${(cells[name]%3)*50}%`,'--icon-y':`${Math.floor(cells[name]/3)*50}%`}"><span>{{ fallback[name] || '🌱' }}</span></span></template>
