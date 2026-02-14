// Test script for LaunchBox chat endpoint
// Run with: node test_launchbox_chat.js

async function testLaunchBoxChat() {
  try {
    console.log('Testing /api/launchbox/chat endpoint...')

    const response = await fetch('http://localhost:8787/api/launchbox/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: 'What games do you have?',
        context: {
          currentFilters: {
            genre: 'All',
            platform: 'All',
            decade: 'All',
            sortBy: 'title',
            search: ''
          },
          availableGames: 15,
          totalGames: 15,
          stats: {
            total_games: 15,
            platforms_count: 3,
            genres_count: 10
          }
        }
      })
    })

    if (!response.ok) {
      console.error(`Error: HTTP ${response.status}`)
      const text = await response.text()
      console.error('Response:', text)
      return
    }

    const result = await response.json()
    console.log('Success!')
    console.log('Response:', result.response)
    if (result.game_launched) {
      console.log('Game was launched!')
    }
  } catch (error) {
    console.error('Failed to test endpoint:', error)
  }
}

// Run the test
testLaunchBoxChat()