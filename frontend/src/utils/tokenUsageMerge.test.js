import {test} from 'node:test'
import assert from 'node:assert/strict'
import {mergeTokenUsageEvents} from './tokenUsageMerge.js'
const row = (id,model='a',agent='Dev') => ({usage_id:id,created_at:100,model,agent_name:agent,input_tokens:9,output_tokens:1,total_tokens:10,cached_tokens:3,est_cost:0.01,pricing_source:'fallback'})
function snapshot(){ return {snapshot_id:5,window_start:50,totals:{total_tokens:50,llm_calls:5},agents:[],models:[]} }
test('REST-covered and duplicated SSE rows are never counted twice',()=>{
 const data=snapshot()
 mergeTokenUsageEvents(data,[row(4),row(5),row(6),row(6)])
 mergeTokenUsageEvents(data,[row(6)])
 assert.equal(data.totals.total_tokens,60)
 assert.equal(data.totals.llm_calls,6)
})
test('runtime model switches retain each call attribution',()=>{
 const data=snapshot()
 mergeTokenUsageEvents(data,[row(6,'a'),row(7,'b')])
 assert.deepEqual(data.models.map(m=>[m.model,m.total_tokens]),[['a',10],['b',10]])
 assert.equal(data.totals.unverified_pricing_calls,2)
})
test('agent and time filters apply to live events',()=>{
 const data=snapshot();data.agent_filter='Dev'
 mergeTokenUsageEvents(data,[row(6,'a','QE'),{...row(7),created_at:40},row(8)])
 assert.equal(data.totals.total_tokens,60)
})

test('long open dashboards request a fresh snapshot before dedup state grows unbounded',()=>{
 const data=snapshot()
 const refresh=mergeTokenUsageEvents(data,Array.from({length:4096},(_,i)=>row(i+6)))
 assert.equal(refresh,true)
 assert.ok(data._liveUsageIds.size<=2048)
 const total=data.totals.total_tokens
 assert.equal(mergeTokenUsageEvents(data,[row(9000)]),true)
 assert.equal(data.totals.total_tokens,total)
})
