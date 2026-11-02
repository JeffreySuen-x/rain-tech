/** Encode mono PCM as a standard 16-bit WAV; no network or codec service. */
export function encodeWav(chunks, sampleRate) {
  const length=chunks.reduce((sum,chunk)=>sum+chunk.length,0)
  const data=new ArrayBuffer(44+length*2),view=new DataView(data)
  const word=(offset,text)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i))}
  word(0,'RIFF');view.setUint32(4,36+length*2,true);word(8,'WAVE');word(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);word(36,'data');view.setUint32(40,length*2,true)
  let index=44;for(const chunk of chunks)for(const value of chunk){const v=Math.max(-1,Math.min(1,value));view.setInt16(index,v<0?v*32768:v*32767,true);index+=2}
  return new Blob([data],{type:'audio/wav'})
}
