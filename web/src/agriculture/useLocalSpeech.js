import { ref, onBeforeUnmount } from 'vue'
export function useLocalSpeech() {
  const speaking = ref(false), speechMessage = ref(''); let generation = 0
  function stop() { ++generation; globalThis.speechSynthesis?.cancel(); speaking.value = false }
  function speak(text) {
    stop()
    const synth = globalThis.speechSynthesis
    const voice = synth?.getVoices().find(v => v.localService === true && /^zh(?:-|$)/i.test(v.lang))
    if (!voice || !globalThis.SpeechSynthesisUtterance) { speechMessage.value = '本机没有可用的中文语音，请稍后重试或阅读文字；未连接外部朗读服务。'; return }
    const chunks = String(text || '').slice(0, 18000).match(/[^。！？\n]{1,180}[。！？\n]?/g) || []
    const token = generation; let i = 0
    speechMessage.value = String(text || '').length > 18000 ? '本次朗读前18000字，可随时停止。' : '使用本机中文语音，可随时停止。'
    function next() { if (token !== generation) return; if (i >= chunks.length) { speaking.value = false; return } const utterance = new SpeechSynthesisUtterance(chunks[i++]); utterance.voice = voice; utterance.lang = voice.lang; utterance.onend = next; utterance.onerror = () => { if(token === generation) { speaking.value = false; speechMessage.value = '朗读未完成，请阅读文字。' } }; speaking.value = true; synth.speak(utterance) }
    next()
  }
  onBeforeUnmount(stop)
  return { speaking, speechMessage, speak, stop }
}
