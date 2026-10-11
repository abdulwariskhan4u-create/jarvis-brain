import test from 'node:test'
import assert from 'node:assert/strict'
import { meetingOutcome, meetingRound } from './meetingPresentation.js'

test('round exhaustion is a warning, never acceptance', () => {
  for (const outcome of ['max_rounds', 'max_rounds_reached']) {
    assert.deepEqual(meetingOutcome(outcome), { tone: 'warning', icon: '◼', labelKey: 'meetings.statusMaxRoundsShort' })
  }
  assert.equal(meetingRound({ current_round: 3, max_rounds: 2, ended: true }), 2)
})
test('only explicit pass or consensus renders success; fail stays danger', () => {
  assert.equal(meetingOutcome('verdict_pass').tone, 'success')
  assert.equal(meetingOutcome('VERDICT_PASS').tone, 'success')
  assert.equal(meetingOutcome('consensus').tone, 'success')
  assert.equal(meetingOutcome('verdict_fail').tone, 'danger')
  assert.equal(meetingOutcome('all_left').tone, 'neutral')
  assert.equal(meetingOutcome('unknown').tone, 'neutral')
  assert.equal(meetingOutcome(null).tone, 'neutral')
})
test('round handles missing, invalid and live state without hiding active progress', () => {
  assert.equal(meetingRound({}, { current_round: 2 }), 2)
  assert.equal(meetingRound({ current_round: 3, max_rounds: 2, ended: false }), 3)
  assert.equal(meetingRound({ current_round: 'invalid' }), 1)
  assert.equal(meetingRound({ current_round: -1 }), 1)
})
