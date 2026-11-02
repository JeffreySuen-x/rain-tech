// Presentation-only topics; every result remains a current authorized knowledge item.
const textOf = item => [item.title,item.name,item.category,...(item.excerpts||[]).map(x=>x.text)].filter(Boolean).join(' ')
export const learningTopics = [
 {id:'grapes',title:'葡萄种植',pattern:/葡萄|栽培|修剪|果穗|花期/},
 {id:'water',title:'土壤与水分',pattern:/土壤|水分|灌溉|滴灌|湿度|浇水/},
 {id:'field',title:'田间观察',pattern:/叶片|叶背|病斑|病害|田间|观察|结露|巡园/},
]
export function topicItems(items,topic='') {
 const rule=learningTopics.find(x=>x.id===topic)
 return rule ? items.filter(item=>rule.pattern.test(textOf(item))) : items
}
export function agriculturalItems(items) { return items.filter(item=>learningTopics.some(topic=>topic.pattern.test(textOf(item)))) }
