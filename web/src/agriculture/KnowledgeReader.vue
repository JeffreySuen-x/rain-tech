<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import ReaderContent from './ReaderContent.js'
import { findReaderAnchor, parseDocument } from './reader-markdown.js'
import './reader.css'
const props=defineProps({item:Object,text:{type:String,default:''},items:{type:Array,default:()=>[]},selected:{type:Array,default:()=>[]},loading:Boolean,error:String,downloadUrl:String,fragment:String,speaking:Boolean,speechMessage:String})
const emit=defineEmits(['ask','close','toggle','article','speak','stop','learn'])
const excerpt=ref(''), moreOpen=ref(false), fontOpen=ref(false)
function captureSelection(event){
  if(event?.target?.closest?.('.concept-reader-actions, .reader-selection-ask'))return
  const selection=window.getSelection(), article=body.value?.querySelector('.reader-article')
  const valid=selection?.rangeCount && article?.contains(selection.anchorNode) && article.contains(selection.focusNode)
  const text=valid?selection.toString().trim():''
  excerpt.value=text.length<=1200?text:''
}
const size=ref('standard'),spacing=ref('comfortable'),sourceOpen=ref(false),tocOpen=ref(false),message=ref(''),body=ref(null)
const document=computed(()=>parseDocument(props.text))
const rawLines=computed(()=>props.text.split(/\r?\n/))
async function jump(fragment) {
  const id=findReaderAnchor(document.value.toc,fragment)
  if(!id){message.value='文章中没有对应的章节';return}
  // IDs originate solely from our parser; no arbitrary selectors from source links.
  sourceOpen.value=false
  await nextTick()
  const target=body.value?.querySelector(`[id="${id}"]`)
  if(target){target.scrollIntoView?.({block:'start'});target.focus?.({preventScroll:true})}
  tocOpen.value=false
}
function navigate(target){message.value='';if(target.kind==='article')emit('article',target);else if(target.kind==='anchor')jump(target.fragment);else message.value=target.message||'链接不可用'}
watch(()=>[props.item?.id,props.text],async()=>{sourceOpen.value=false;moreOpen.value=false;fontOpen.value=false;tocOpen.value=false;excerpt.value='';message.value='';body.value?.scrollTo?.({top:0});if(props.fragment&&props.text){await nextTick();jump(props.fragment)}})
</script>
<template>
<section class="knowledge-reading-layer" :class="[`reader-size-${size}`,`reader-spacing-${spacing}`]" aria-label="知识阅读器" @mouseup="captureSelection" @touchend="captureSelection" @keyup="captureSelection">
  <header class="reader-toolbar"><button class="reader-back" @click="emit('close')">← 学习</button><button :aria-expanded="tocOpen" @click="tocOpen=!tocOpen">目录</button><button :aria-expanded="fontOpen" aria-label="阅读字号与行距" @click="fontOpen=!fontOpen">Aa</button><button :aria-expanded="moreOpen" @click="moreOpen=!moreOpen">更多 ···</button></header>
  <section v-if="fontOpen" class="reader-more"><label>字号<select v-model="size" aria-label="阅读字号"><option value="small">小</option><option value="standard">标准</option><option value="large">大</option></select></label><label>行距<select v-model="spacing" aria-label="阅读行距"><option value="compact">紧凑</option><option value="comfortable">舒适</option></select></label></section><section v-if="moreOpen" class="reader-more"><button @click="sourceOpen=!sourceOpen;moreOpen=false">{{ sourceOpen?'继续阅读':'原文与来源' }}</button><button v-if="item" :disabled="loading || !!error" :aria-pressed="selected.includes(item.id)" @click="emit('toggle',item.id)">{{ selected.includes(item.id)?'取消本轮引用':'加入本轮引用' }}</button><button :disabled="loading || !!error" @click="emit('learn',item)">写下这次学到的</button></section>
  <p v-if="speechMessage" class="reader-message" role="status">{{ speechMessage }}</p><p v-if="message" class="reader-message" role="status">{{ message }}</p>
  <div class="reader-layout" :class="{'reader-with-toc':tocOpen}"><aside v-if="tocOpen" class="reader-toc"><button class="reader-toc-toggle" @click="tocOpen=!tocOpen" :aria-expanded="tocOpen">章节目录 {{ tocOpen?'收起':'展开' }}</button><nav :class="{'toc-expanded':tocOpen}" aria-label="文章目录"><p>本篇目录</p><button v-for="entry in document.toc" :key="entry.id" :class="`toc-level-${entry.level}`" @click="jump(entry.id)">{{ entry.text.replace(/[*_`]/g,'') }}</button><small v-if="!document.toc.length">本篇暂无分节标题</small></nav></aside>
  <div ref="body" class="reader-scroll"><p v-if="loading" class="reader-state" role="status">正在读取完整原文…</p><p v-else-if="error" class="reader-state agri-error" role="alert">{{ error }}</p><section v-else-if="sourceOpen" class="reader-sources"><h2>原文与来源</h2><dl><dt>文章</dt><dd>{{ item?.title }} {{ item?.library?.articleId }}</dd><dt>存储版本</dt><dd>{{ item?.version ?? '未提供' }}</dd><template v-if="item?.library?.sourceVersion"><dt>教程版本</dt><dd>{{ item.library.sourceVersion }}</dd></template><dt>SHA256</dt><dd>{{ item?.sourceHash || '未提供' }}</dd><dt v-if="item?.library?.sourceRelativePath">来源目录标识</dt><dd v-if="item?.library?.sourceRelativePath">{{ item.library.sourceRelativePath }}</dd></dl><a v-if="downloadUrl" :href="downloadUrl" download>下载完整原件</a><p>行号对应原始文本。阅读视图隐藏的开头元数据保留在这里。</p><div class="reader-source-lines"><div v-for="(line,i) in rawLines" :key="i"><small>L{{ i+1 }}</small><pre>{{ line || ' ' }}</pre></div></div></section><article v-else class="reader-article"><h1 v-if="!document.blocks.some(x=>x.type==='heading'&&x.level===1)">{{ item?.title }}</h1><p v-if="document.fallback" class="reader-message">此文档使用完整纯文本阅读。</p><ReaderContent :document="document" :item="item" :authorized-items="items" @navigate="navigate" /></article></div></div>
<button v-if="excerpt && !loading && !error" class="reader-selection-ask" @mousedown.prevent @click="emit('ask',item,excerpt)">问问这段</button><footer class="concept-reader-actions"><button :disabled="loading || !!error || !text" @click="emit(speaking ? 'stop' : 'speak')">{{ speaking ? '停止朗读' : '听文章' }}</button><button :disabled="loading || !!error || !text" @click="emit('ask',item)">问问这篇</button></footer></section>
</template>
