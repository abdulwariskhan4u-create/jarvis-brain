/** Merge persisted call events into a REST snapshot, once per usage row. */
export function mergeTokenUsageEvents(data, events) {
  if (!data || !Number.isInteger(data.snapshot_id)) return
  if (data._needsSnapshot) return true
  const seen = data._liveUsageIds || (data._liveUsageIds = new Set())
  const fields = ['input_tokens','output_tokens','total_tokens','cached_tokens','reasoning_tokens','est_cost']
  function accumulate(target, event) {
    for (const field of fields) target[field] = (target[field] || 0) + (event[field] || 0)
    target.llm_calls = (target.llm_calls || 0) + 1
    target.unverified_pricing_calls = (target.unverified_pricing_calls || 0) + (event.pricing_source === 'configured' ? 0 : 1)
  }
  for (const event of events) {
    const id = event.usage_id
    if (!Number.isInteger(id) || id <= data.snapshot_id || seen.has(id)) continue
    if (data.agent_filter && event.agent_name !== data.agent_filter) continue
    if (event.created_at < (data.window_start || 0)) continue
    if (seen.size >= 2048) {
      data._needsSnapshot = true
      return true
    }
    seen.add(id)
    accumulate(data.totals || (data.totals = {}), event)
    for (const [collection, key, value] of [['agents','agent_name',event.agent_name],['models','model',event.model]]) {
      const rows = data[collection] || (data[collection] = [])
      let row = rows.find(row => row[key] === value)
      if (!row) { row = {[key]:value};rows.push(row) }
      accumulate(row, event)
      if (collection === 'models') {
        const source = event.pricing_source || 'historical_unverified'
        row.pricing_sources ||= []
        if (!row.pricing_sources.includes(source)) row.pricing_sources.push(source)
      }
    }
  }
  data.agents?.sort((a,b)=>b.total_tokens-a.total_tokens)
  data.models?.sort((a,b)=>b.total_tokens-a.total_tokens)
  return false
}
