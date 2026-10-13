import { test, expect } from '@playwright/test'
import { dirname,join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { mockBackend,seedApiKey } from '../harness'
const fixtures=join(dirname(fileURLToPath(import.meta.url)),'..','fixtures')

test('chat HTTP failure shows the actionable server error and unlocks composer',async({page})=>{
 await seedApiKey(page)
 await mockBackend(page,[join(fixtures,'_app_boot_noise.yaml'),join(fixtures,'chat_streaming_happy.yaml')])
 await page.route('**/api/chat-stream',r=>r.fulfill({status:503,json:{detail:'Agent runtime is still starting. Retry shortly.'}}))
 await page.goto('/chat')
 const input=page.getByPlaceholder(/type a message/i)
 await input.fill('Continue existing team')
 await input.press('Enter')
 await expect(page.getByText('Agent runtime is still starting. Retry shortly.',{exact:false})).toBeVisible()
 await expect(input).toBeEnabled()
 await expect(page.getByText('Unknown error',{exact:true})).toHaveCount(0)
})

test('persisted REST and duplicated SSE calls reconcile without double counting',async({page})=>{
 await seedApiKey(page)
 await mockBackend(page,[join(fixtures,'_app_boot_noise.yaml')])
 const base={snapshot_id:5,window_start:0,agent_filter:'',totals:{total_tokens:50,input_tokens:45,output_tokens:5,llm_calls:5,est_cost:0},agents:[],models:[]}
 await page.route('**/api/metrics/tokens**',r=>r.fulfill({json:base}))
 const event=(id:number,model:string)=>({event_type:'token_usage',agent_name:'QE',timestamp:100,data:{usage_id:id,created_at:100,model,pricing_source:'fallback',total_tokens:10,input_tokens:9,output_tokens:1,est_cost:0}})
 await page.route('**/api/agents/activity-stream**',r=>r.fulfill({headers:{'content-type':'text/event-stream'},body:'retry: 3600000\n\n'+[event(5,'a'),event(6,'a'),event(6,'a'),event(7,'b')].map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')}))
 await page.goto('/token-usage')
 await expect(page.getByRole('heading',{level:1})).toContainText('70 tokens')
 await expect(page.getByText('7 llm calls',{exact:true})).toBeVisible()
 await expect(page.locator('.tokens__model-name').filter({hasText:/^[ab]$/})).toHaveCount(2)
 await page.getByRole('button',{name:'7D',exact:true}).click()
 await expect(page.getByRole('heading',{level:1})).toContainText('70 tokens')
 await expect(page.getByText('7 llm calls',{exact:true})).toBeVisible()
})

test('monitor renders resumed runs with overlapping turn indices without losing their messages',async({page})=>{
 await seedApiKey(page)
 await mockBackend(page,[join(fixtures,'_app_boot_noise.yaml'),join(fixtures,'agent_monitor_live.yaml')])
 const duplicateKeys:string[]=[]
 page.on('console',msg=>{if(msg.text().includes('Duplicate keys'))duplicateKeys.push(msg.text())})
 const turn=(run:string,idx:number,text:string)=>({run_id:run,turn_idx:idx,role:'assistant',timestamp:idx+1,message:{role:'assistant',content:[{type:'text',text}]}})
 await page.route('**/api/agents/*/messages**',r=>r.fulfill({json:{turns:r.request().url().includes('alpha-agent')?[turn('old',0,'OLD-RUN-VERIFIED'),turn('old',1,'OLD-RUN-CHECKPOINT'),turn('new',0,'NEW-RUN-VERIFIED'),turn('new',1,'NEW-RUN-CHECKPOINT')]:[]}}))
 await page.goto('/monitor')
 const card=page.locator('.agent-terminal').filter({hasText:'alpha-agent'})
 await expect(card.getByText('OLD-RUN-VERIFIED',{exact:true})).toBeVisible()
 await expect(card.getByText('NEW-RUN-VERIFIED',{exact:true})).toBeVisible()
 await expect(card.getByText('OLD-RUN-CHECKPOINT',{exact:true})).toBeVisible()
 await expect(card.getByText('NEW-RUN-CHECKPOINT',{exact:true})).toBeVisible()
 expect(duplicateKeys).toEqual([])
})
