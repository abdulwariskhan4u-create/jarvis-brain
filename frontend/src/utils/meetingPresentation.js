/** Ended is a lifecycle state; acceptance requires an explicit outcome. */
export function meetingOutcome(value) {
  const outcome = String(value || '').toLowerCase()
  if (outcome === 'verdict_pass' || outcome === 'consensus') {
    return { tone: 'success', icon: '✓', labelKey: outcome === 'consensus' ? 'meetings.statusConsensus' : 'meetings.statusAccepted' }
  }
  if (outcome === 'verdict_fail') return { tone: 'danger', icon: '×', labelKey: 'meetings.statusRejected' }
  if (outcome === 'max_rounds' || outcome === 'max_rounds_reached') {
    return { tone: 'warning', icon: '◼', labelKey: 'meetings.statusMaxRoundsShort' }
  }
  return { tone: 'neutral', icon: '◼', labelKey: 'meetings.statusEnded' }
}

export function meetingRound(meeting = {}, state = {}) {
  const raw = Number(state.current_round ?? meeting.current_round ?? 1)
  const round = Number.isFinite(raw) ? Math.max(1, Math.floor(raw)) : 1
  const max = Number(state.max_rounds ?? meeting.max_rounds)
  return (state.ended ?? meeting.ended) && Number.isFinite(max) && max > 0 ? Math.min(round, max) : round
}
