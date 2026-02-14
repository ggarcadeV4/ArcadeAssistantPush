import request from 'supertest'
import express from 'express'
import registerAIRoutes from '../../gateway/routes/ai.js'

const app = express()
app.use(express.json())
registerAIRoutes(app)

test('400 when messages missing', async () => {
  const r = await request(app)
    .post('/api/ai/chat')
    .set('x-scope', 'state')
    .send({})

  expect(r.status).toBe(400)
  expect(r.body.code).toBe('BAD_REQUEST')
})

// Note: Tool passthrough tests require real API keys or more complex mocking setup
// For now, we verify the route accepts tools parameter without error
test('accepts tools parameter without error (requires API key for full test)', async () => {
  const tools = [
    {
      name: 'launch_game',
      description: 'Launch a game from LaunchBox',
      input_schema: {
        type: 'object',
        properties: {
          game_id: { type: 'string', description: 'The game ID to launch' }
        },
        required: ['game_id']
      }
    }
  ]

  const r = await request(app)
    .post('/api/ai/chat')
    .set('x-scope', 'state')
    .send({
      provider: 'claude',
      messages: [{ role: 'user', content: 'Launch MAME game 12345' }],
      tools
    })

  // Will fail with NOT_CONFIGURED (501) if no API key is set, which is expected
  // The important part is that it doesn't fail with a parsing error
  expect([200, 501]).toContain(r.status)
  if (r.status === 501) {
    expect(r.body.code).toBe('NOT_CONFIGURED')
  }
  // If 200, tools were accepted and processed successfully
})

