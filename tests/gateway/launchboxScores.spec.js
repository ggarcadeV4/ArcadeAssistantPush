import request from 'supertest'
import { jest } from '@jest/globals'
import express from 'express'
import router from '../../gateway/routes/launchboxScores.js'

// Helper to mount the router for tests
function makeApp() {
  const app = express()
  app.use(express.json())
  app.use('/api/launchbox/scores', router)
  return app
}

describe('scores proxy', () => {
  let app
  beforeEach(() => {
    app = makeApp()
    global.fetch = jest.fn()
  })

  test('happy path returns fresh leaderboard', async () => {
    const payload = { leaderboard: [{ gameId: 'g1', bestScore: 100, bestPlayer: 'Sam' }] }
    global.fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload })

    const r = await request(app)
      .get('/api/launchbox/scores/leaderboard?limit=5')
      .set('x-panel', 'launchbox')

    expect(r.status).toBe(200)
    expect(r.body.leaderboard).toBeDefined()
    expect(r.body.cached).toBeUndefined()
  })

  test('circuit breaker serves cached with cached:true', async () => {
    const payload = { leaderboard: [{ gameId: 'g1', bestScore: 100, bestPlayer: 'Sam' }] }
    global.fetch
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => payload }) // prime cache
      .mockRejectedValueOnce(new Error('plugin down')) // next call fails

    // Prime cache
    const r1 = await request(app).get('/api/launchbox/scores/leaderboard?limit=5')
    expect(r1.status).toBe(200)

    // Failure should trigger cached response
    const r2 = await request(app).get('/api/launchbox/scores/leaderboard?limit=5')
    expect(r2.status).toBe(200)
    expect(r2.body.cached).toBe(true)
  })

  test('offline without cache returns 503 friendly', async () => {
    global.fetch.mockRejectedValueOnce(new Error('plugin down'))
    const r = await request(app).get('/api/launchbox/scores/by-game?gameId=abc')
    expect(r.status).toBe(503)
    expect(r.body.error).toBe('plugin_unavailable')
  })
})
