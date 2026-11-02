<script setup>
import { learningTopics, topicItems, agriculturalItems } from './mobile-learning.js'
import FriendlyIcon from './FriendlyIcon.vue'
import { computed, ref, watch } from 'vue'
import { libraryPage, libraryTracks, memberships, knowledgePreview } from './library.js'
const props = defineProps({items:{type:Array,default:()=>[]}, selected:{type:Array,default:()=>[]}})
const emit = defineEmits(['read','listen','voice','learn','toggle','upload','ask'])
const mobileExpanded=ref(false), mobileTopic=ref('')
const query=ref(''), track=ref(''), group=ref(''), page=ref(1)
const tracks=computed(()=>libraryTracks(props.items)), tutorials=computed(()=>props.items.filter(x=>x.library).length)
const result=computed(()=>libraryPage(props.items,{query:query.value,track:track.value,group:group.value,page:page.value}))
watch([query,track,group],()=>page.value=1)
function choose(id) { track.value=id; group.value='' }
const mainTracks=computed(()=>tracks.value.filter(entry=>['monitoring','agricultural_skill_learning'].includes(entry.id.toLowerCase())))
const trackName=id=>({monitoring:'看懂作物',agricultural_skill_learning:'学会农活'})[id.toLowerCase()] || id
const starters=computed(()=>{const rules=[{articleId:'MON-032',alias:'夜间结露怎么看？',cover:'dew'},{articleId:'EDU-004',alias:'土壤水分怎么读？',cover:'soil'},{articleId:'EDU-001',alias:'农活怎样一步步学？',cover:'book'},{articleId:'EDU-023',alias:'现场问题怎么说清？',cover:'camera'}];return rules.flatMap(rule=>{const item=props.items.find(item=>item.library?.articleId===rule.articleId);return item?[{...rule,item}]:[]})})
const recommendation=computed(()=>{const items=agriculturalItems(props.items);return items.find(item=>/叶|病斑/.test(item.title||item.name||'')) || items[0]})
const mobileResults=computed(()=>topicItems(libraryPage(props.items,{query:query.value,page:1,size:props.items.length||12}).items,mobileTopic.value))
const showRecommendation=computed(()=>Boolean(recommendation.value && !query.value.trim() && !mobileTopic.value))
const mobileRows=computed(()=>{
 const rows=mobileResults.value
 if(query.value.trim() || mobileTopic.value)return rows
 const agricultural=new Set(agriculturalItems(rows).map(item=>item.id))
 const priority=rows.filter(item=>agricultural.has(item.id)||item.library)
 return [...priority,...rows.filter(item=>!agricultural.has(item.id)&&!item.library)]
})
const summary=knowledgePreview
function cover(item){const title=item.title||item.name||'';if(/露|结露|湿度/.test(title))return 'dew';if(/土壤|灌溉|水分/.test(title))return 'soil';if(/照片|拍摄|拍照/.test(title))return 'camera';if(/叶|病害|病斑/.test(title))return 'leaf';return 'book'}
</script>
<template>
<section class="agri-card library-browser">
<div class="mobile-learning-home"><header class="concept-learning-header"><h2>学习</h2><button @click="emit('upload')">导入资料</button></header><div class="concept-learning-hero"><h1>今天想了解什么？</h1><p>从农业资料中找到答案</p><img src="/brand/shuyu-raindrop-v1.png" alt="澍雨水滴"></div><p>{{ items.length }} 份资料</p><div class="mobile-learning-search"><input v-model="query" placeholder="想了解哪方面？" aria-label="搜索学习资料"></div><div class="mobile-learning-chips"><button :class="{selected:!mobileTopic}" @click="mobileTopic=''">全部知识</button><button v-for="entry in learningTopics" :key="entry.id" :class="{selected:mobileTopic===entry.id}" @click="mobileTopic=entry.id">{{ entry.title }}</button></div>  <section v-if="showRecommendation" class="mobile-learning-feature"><h3>推荐阅读</h3><article><div class="knowledge-cover" :class="`cover-${cover(recommendation)}`" aria-hidden="true"></div><h3>{{ recommendation.title || recommendation.name }}</h3><p>{{ summary(recommendation).slice(0,60) }}</p><button @click="emit('read',recommendation)">开始阅读 <span aria-hidden="true">›</span></button></article></section>
<h3>{{ query || mobileTopic ? '查找结果' : '田间实用知识' }}</h3><button v-for="item in mobileRows" :key="item.id" class="mobile-learning-row" @click="emit('read',item)"><span class="knowledge-cover" :class="`cover-${cover(item)}`"><small>学习示意</small></span><span><strong>{{ item.title || item.name }}</strong><small class="mobile-learning-category">{{ item.category || (item.library ? '农业学习资料' : '我的资料') }}</small><small class="mobile-learning-summary">{{ summary(item).slice(0,90) }}</small><em>阅读 ›</em></span><span aria-hidden="true">›</span></button><p v-if="!mobileRows.length" role="status">暂无匹配资料，请调整关键词或分组。</p><button v-if="showRecommendation" class="mobile-learning-ask" @click="emit('ask',recommendation)">读到不懂的地方，就问澍雨　›</button></div><div class="learning-management" :class="{expanded:mobileExpanded}"><button class="learning-management-toggle" :aria-expanded="mobileExpanded" @click="mobileExpanded=!mobileExpanded">全部资料与管理 · {{ result.total }} 份</button><div class="learning-management-body"><div class="agri-section-title"><div><h2>学一点，用得上</h2><p>农业知识库 · 完整原文，随时查阅</p></div><button @click="emit('upload')">上传资料</button></div>
  <p class="library-count"><strong>{{ tutorials }}</strong> 篇教程 · 全部 {{ items.length }} 份资料 · 已选 {{ selected.length }} 条引用</p>
  <details class="library-disclosure"><summary>资料说明</summary><p class="agri-muted">原创教程、解释与合成练习，用于学习和核对；并非专家签审或独立研究成果。阅读和搜索不会调用模型，加入引用后才随发送交给助手。听讲会先读取受权原文，再使用本机中文语音；不自动加入引用。</p></details>

  <div class="library-tracks library-main-tracks"><button v-for="entry in mainTracks" :key="entry.id" :class="{selected:track===entry.id}" @click="choose(entry.id)"><FriendlyIcon :name="entry.id.toLowerCase() === 'monitoring' ? 'leaf' : 'book'"/><span><strong>{{ trackName(entry.id) }}</strong><small>{{ entry.count }} 篇</small></span></button><button :class="{selected:track==='mine'}" @click="choose('mine')"><FriendlyIcon name="folder"/><span><strong>我的资料</strong><small>{{ items.length-tutorials }} 份</small></span></button></div><div class="library-small-tracks"><button :class="{selected:!track}" @click="choose('')">全部资料</button><button v-for="entry in tracks.filter(entry=>!mainTracks.includes(entry))" :key="entry.id" :class="{selected:track===entry.id}" @click="choose(entry.id)">{{ entry.id==='shared' ? '共同基础' : entry.title }} · {{ entry.count }}</button><details v-if="tracks.some(entry=>entry.id===track)"><summary>分组说明</summary>{{ tracks.find(entry=>entry.id===track)?.title }}</details></div>
  <div class="workspace-filters"><input v-model="query" placeholder="搜索全库：标题、文章 ID、分组或正文" aria-label="搜索全部知识正文"><button @click="emit('voice')">🎙 语音提问</button><select v-if="tracks.some(x=>x.id===track)" v-model="group" aria-label="教程分组"><option value="">全部分组</option><option v-for="entry in tracks.find(x=>x.id===track)?.groups || []" :key="entry.id" :value="entry.id">{{ entry.title }}</option></select></div>
  <section v-if="!query.trim() && !track && result.page === 1 && starters.length" class="library-starters"><h3>从这里开始</h3><div class="knowledge-grid"><article v-for="entry in starters" :key="entry.item.id" class="agri-task"><div class="knowledge-cover" :class="`cover-${entry.cover}`" aria-hidden="true"><span>学习示意 · AI插画</span></div><h3>{{ entry.alias }}</h3><small>{{ entry.item.title || entry.item.name }}</small><p>{{ summary(entry.item).slice(0,70) }}</p><div class="library-actions"><button aria-label="阅读原文" @click="emit('read',entry.item)">📖 阅读</button><button @click="emit('listen',entry.item)">🔊 听讲</button></div></article></div></section><h3 class="library-all-heading"><span class="learning-desktop-label">全部资料</span><span class="learning-mobile-label">田间实用知识</span></h3>
  <p class="agri-muted" role="status">找到 {{ result.total }} 份 · 第 {{ result.page }} / {{ result.pages }} 页</p>
  <div class="knowledge-grid"><article v-for="item in result.items" :key="item.id" class="agri-task"><div class="knowledge-cover" :class="`cover-${cover(item)}`" aria-hidden="true"><span>学习示意 · AI插画</span></div><small class="knowledge-category">{{ item.library?.articleId || '我的资料' }} · {{ item.category || '园区资料' }} · {{ item.library ? '原创教程' : '已存资料' }}</small><h3>{{ item.title || item.name }}</h3><small v-if="memberships(item).length">{{ memberships(item).map(m=>[m.groupTitle,m.sectionLabel].filter(Boolean).join(' / ')).join(' · ') }}</small><p>{{ summary(item) }}</p><p v-if="memberships(item).find(m=>m.readingGoal)" class="library-goal">学习目标：{{ memberships(item).find(m=>m.readingGoal).readingGoal }}</p><div class="library-actions"><button @click="emit('read',item)">阅读原文</button><button @click="emit('learn',item)">记录学习反馈</button><button :aria-pressed="selected.includes(item.id)" @click="emit('toggle',item.id)">{{ selected.includes(item.id) ? '取消引用' : '加入对话引用' }}</button></div></article></div>
  <p v-if="!result.total" class="agri-muted">暂无匹配资料，请调整关键词或分组。上传的园区资料也会显示在这里。</p>
  <nav class="library-pagination" aria-label="知识分页"><button :disabled="result.page===1" @click="page=result.page-1">上一页</button><span>{{ result.page }} / {{ result.pages }} · 每页 12 篇</span><button :disabled="result.page===result.pages" @click="page=result.page+1">下一页</button></nav>
</div></div><slot />
</section>
</template>

<style src="./mobile-learning.css"></style>
