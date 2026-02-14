# LaunchBox Tool Calling Fix
**Date:** 2025-10-09
**Problem:** LoRa AI chat executes tools but doesn't complete multi-step actions (e.g., "Launch Pac-Man")
**Status:** Implementation Plan

---

## Problem Statement

### What's Happening Now

When a user types "Launch Pac-Man" in LoRa's chat:

1. ✅ User message sent to `/api/launchbox/chat`
2. ✅ Claude API called with tools
3. ✅ Claude returns `tool_use` block: `search_games` with query "Pac-Man"
4. ✅ Gateway executes `launchboxTools.search_games({ query: "Pac-Man" })`
5. ✅ Tool returns 31 matching games with IDs
6. ❌ **Gateway appends result to text and returns to user**
7. ❌ **Claude never sees the search results**
8. ❌ **Claude never calls `launch_game` tool**
9. ❌ **Game never launches**

**Current code location:** `gateway/routes/launchboxAI.js` lines 179-214 (`processResponse()` function)

### Why It's Broken

The current implementation treats tool execution as a **one-shot operation**:

```javascript
// Current (BROKEN) flow:
async function processResponse(response) {
  for (const block of response.content) {
    if (block.type === 'tool_use') {
      const toolResult = await toolFunction(block.input);
      // ❌ Just append result to text
      finalText += formatToolResult(block.name, toolResult);
    }
  }
  // ❌ Return without calling Claude again
  return { text: finalText, toolCalls };
}
```

**The problem:** This doesn't implement the Anthropic tool calling loop. Claude needs to receive the tool results and decide what to do next.

---

## The Correct Architecture

### Anthropic Tool Calling Loop (Official Pattern)

According to Anthropic's API documentation, tool calling requires multiple round-trips:

```
┌─────────────────────────────────────────────────────────────┐
│ Round 1: Initial Request                                    │
├─────────────────────────────────────────────────────────────┤
│ messages: [                                                 │
│   { role: 'user', content: 'Launch Pac-Man' }              │
│ ]                                                           │
│ tools: [search_games, launch_game, ...]                    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Response 1: Tool Use                                        │
├─────────────────────────────────────────────────────────────┤
│ stop_reason: "tool_use"                                     │
│ content: [                                                  │
│   {                                                         │
│     type: "text",                                           │
│     text: "I'll search for Pac-Man first..."               │
│   },                                                        │
│   {                                                         │
│     type: "tool_use",                                       │
│     id: "toolu_01A1B2C3D4E5F6",                            │
│     name: "search_games",                                   │
│     input: { query: "Pac-Man" }                             │
│   }                                                         │
│ ]                                                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Our Code Executes: search_games({ query: "Pac-Man" })      │
│ Result: { success: true, count: 31, games: [...] }         │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Round 2: Tool Result (WE MUST SEND THIS!)                  │
├─────────────────────────────────────────────────────────────┤
│ messages: [                                                 │
│   { role: 'user', content: 'Launch Pac-Man' },             │
│   {                                                         │
│     role: 'assistant',                                      │
│     content: [                                              │
│       { type: 'text', text: "I'll search..." },            │
│       {                                                     │
│         type: 'tool_use',                                   │
│         id: 'toolu_01A1B2C3D4E5F6',                        │
│         name: 'search_games',                               │
│         input: { query: 'Pac-Man' }                         │
│       }                                                     │
│     ]                                                       │
│   },                                                        │
│   {                                                         │
│     role: 'user',                                           │
│     content: [                                              │
│       {                                                     │
│         type: 'tool_result',                                │
│         tool_use_id: 'toolu_01A1B2C3D4E5F6',               │
│         content: '{"success":true,"count":31,"games":[...]}' │
│       }                                                     │
│     ]                                                       │
│   }                                                         │
│ ]                                                           │
│ tools: [search_games, launch_game, ...]                    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Response 2: Second Tool Use                                 │
├─────────────────────────────────────────────────────────────┤
│ stop_reason: "tool_use"                                     │
│ content: [                                                  │
│   {                                                         │
│     type: "text",                                           │
│     text: "I found 31 Pac-Man games. Launching the 1980    │
│            original..."                                     │
│   },                                                        │
│   {                                                         │
│     type: "tool_use",                                       │
│     id: "toolu_02G7H8I9J0K1L2",                            │
│     name: "launch_game",                                    │
│     input: { game_id: "pac-man-1980-id" }                   │
│   }                                                         │
│ ]                                                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Our Code Executes: launch_game({ game_id: "..." })         │
│ Result: { success: true, method_used: "MAME", ... }        │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Round 3: Final Tool Result                                 │
├─────────────────────────────────────────────────────────────┤
│ messages: [                                                 │
│   ... (previous messages) ...,                              │
│   {                                                         │
│     role: 'assistant',                                      │
│     content: [                                              │
│       { type: 'text', text: "Launching..." },              │
│       {                                                     │
│         type: 'tool_use',                                   │
│         id: 'toolu_02G7H8I9J0K1L2',                        │
│         name: 'launch_game',                                │
│         input: { game_id: '...' }                           │
│       }                                                     │
│     ]                                                       │
│   },                                                        │
│   {                                                         │
│     role: 'user',                                           │
│     content: [                                              │
│       {                                                     │
│         type: 'tool_result',                                │
│         tool_use_id: 'toolu_02G7H8I9J0K1L2',               │
│         content: '{"success":true,"method_used":"MAME"}'   │
│       }                                                     │
│     ]                                                       │
│   }                                                         │
│ ]                                                           │
│ tools: [search_games, launch_game, ...]                    │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Response 3: Final Text                                      │
├─────────────────────────────────────────────────────────────┤
│ stop_reason: "end_turn"                                     │
│ content: [                                                  │
│   {                                                         │
│     type: "text",                                           │
│     text: "🎮 Pac-Man (1980) is launching! Enjoy!"         │
│   }                                                         │
│ ]                                                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
                 Return to User
```

### Key Insight

**We need a WHILE LOOP that continues calling Claude until `stop_reason !== 'tool_use'`.**

---

## The Solution

### Refactored Code Structure

Replace the current single-shot handler with a proper tool calling loop:

```javascript
/**
 * POST /api/launchbox/chat
 *
 * Handles multi-turn tool calling loop with Claude
 */
router.post('/chat', async (req, res) => {
  try {
    const { message, context = {} } = req.body;

    // Validation
    if (!message || typeof message !== 'string') {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'Message field is required'
      });
    }

    // Set FastAPI URL for tool execution
    setFastapiUrl(req.app.locals.fastapiUrl);

    // Build system prompt
    const systemPrompt = buildSystemPrompt(context);

    console.log('[LaunchBox AI] User message:', message);

    // Execute tool calling loop
    const result = await executeToolCallingLoop(systemPrompt, message);

    // Return final result
    res.json({
      success: true,
      response: result.finalText,
      tool_calls_made: result.toolCallsMade,
      rounds: result.rounds
    });

  } catch (error) {
    console.error('[LaunchBox AI] Error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * Execute the tool calling loop until Claude stops requesting tools
 */
async function executeToolCallingLoop(systemPrompt, userMessage) {
  const apiKey = process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY;
  if (!apiKey) {
    throw new Error('ANTHROPIC_API_KEY not configured');
  }

  // Initialize conversation
  const messages = [
    {
      role: 'user',
      content: userMessage
    }
  ];

  let continueLoop = true;
  let rounds = 0;
  const maxRounds = 10; // Safety limit
  const toolCallsMade = [];
  let finalText = '';

  // Main tool calling loop
  while (continueLoop && rounds < maxRounds) {
    rounds++;
    console.log(`[LaunchBox AI] Round ${rounds}: Calling Claude...`);

    // Call Claude API
    const response = await callClaudeAPI(systemPrompt, messages);

    console.log(`[LaunchBox AI] Round ${rounds} stop_reason:`, response.stop_reason);

    // Extract text content from this response
    const textBlocks = response.content.filter(b => b.type === 'text');
    const currentText = textBlocks.map(b => b.text).join('\n');
    if (currentText) {
      finalText = currentText; // Keep the latest text
    }

    // Check if Claude wants to use tools
    if (response.stop_reason === 'tool_use') {
      // Extract tool use blocks
      const toolUseBlocks = response.content.filter(b => b.type === 'tool_use');

      console.log(`[LaunchBox AI] Round ${rounds}: ${toolUseBlocks.length} tool(s) requested`);

      // Add assistant's response to conversation (must include ALL content blocks)
      messages.push({
        role: 'assistant',
        content: response.content
      });

      // Execute all tools and build tool_result blocks
      const toolResultBlocks = [];

      for (const toolUse of toolUseBlocks) {
        console.log(`[LaunchBox AI] Executing tool: ${toolUse.name}`, toolUse.input);

        // Execute the tool
        const toolFunction = launchboxTools[toolUse.name];
        if (!toolFunction) {
          console.error(`[LaunchBox AI] Unknown tool: ${toolUse.name}`);

          // Send error as tool result
          toolResultBlocks.push({
            type: 'tool_result',
            tool_use_id: toolUse.id,
            content: JSON.stringify({
              success: false,
              error: `Unknown tool: ${toolUse.name}`
            })
          });
          continue;
        }

        let toolResult;
        try {
          toolResult = await toolFunction(toolUse.input);
        } catch (error) {
          console.error(`[LaunchBox AI] Tool execution error:`, error);
          toolResult = {
            success: false,
            error: error.message
          };
        }

        console.log(`[LaunchBox AI] Tool result:`, JSON.stringify(toolResult).substring(0, 200));

        // Track tool calls for response
        toolCallsMade.push({
          name: toolUse.name,
          input: toolUse.input,
          result: toolResult
        });

        // Build tool_result block
        toolResultBlocks.push({
          type: 'tool_result',
          tool_use_id: toolUse.id,
          content: JSON.stringify(toolResult)
        });
      }

      // Add tool results as a user message
      messages.push({
        role: 'user',
        content: toolResultBlocks
      });

      // Continue loop - Claude will process tool results
      continueLoop = true;

    } else {
      // Claude finished (stop_reason is 'end_turn' or 'max_tokens')
      console.log(`[LaunchBox AI] Conversation complete after ${rounds} round(s)`);
      continueLoop = false;
    }
  }

  // Safety check
  if (rounds >= maxRounds) {
    console.warn(`[LaunchBox AI] Hit max rounds (${maxRounds}), stopping loop`);
  }

  return {
    finalText: finalText || 'I processed your request.',
    toolCallsMade,
    rounds
  };
}

/**
 * Call Claude API with messages
 */
async function callClaudeAPI(systemPrompt, messages) {
  const apiKey = process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY;

  const response = await fetchWithRetry(ANTHROPIC_API, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-3-5-sonnet-20241022',
      max_tokens: 1024,
      system: systemPrompt,
      tools: launchboxToolDefinitions,
      messages: messages
    })
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Anthropic API error ${response.status}: ${errorText}`);
  }

  return await response.json();
}
```

### What Changed

**Before (BROKEN):**
1. Call Claude once
2. Execute any tools returned
3. Append results to text string
4. Return to user

**After (CORRECT):**
1. Call Claude with user message
2. **WHILE** `stop_reason === 'tool_use'`:
   - Execute tools
   - Build `tool_result` messages
   - Add assistant response + tool results to conversation
   - Call Claude again
3. Return final text after loop completes

---

## Implementation Checklist

### Step 1: Update `gateway/routes/launchboxAI.js`

- [ ] Replace `processResponse()` function with `executeToolCallingLoop()`
- [ ] Add `callClaudeAPI()` helper function
- [ ] Update route handler to use new loop
- [ ] Remove old `formatToolResult()` helper (no longer needed)
- [ ] Keep `buildSystemPrompt()` as-is (still needed)

### Step 2: Testing

**Test Case 1: Simple Launch**
```
User: "Launch Pac-Man"
Expected:
  - Round 1: Claude calls search_games
  - Round 2: Claude calls launch_game with first result
  - Round 3: Claude returns success message
  - Game launches
```

**Test Case 2: Multiple Tools**
```
User: "Show me fighting games from the 90s and launch one"
Expected:
  - Round 1: Claude calls filter_games
  - Round 2: Claude calls get_random_game (filtered)
  - Round 3: Claude calls launch_game
  - Game launches
```

**Test Case 3: Tool Error Handling**
```
User: "Launch Super Mario Galaxy 3000"
Expected:
  - Round 1: Claude calls search_games
  - Round 2: Claude receives 0 results
  - Round 3: Claude responds "I couldn't find that game"
  - No crash, graceful error message
```

**Test Case 4: Info Request (No Launch)**
```
User: "What genres do you have?"
Expected:
  - Round 1: Claude calls get_available_genres
  - Round 2: Claude lists genres
  - No game launch
```

### Step 3: Logging & Monitoring

Add to each log statement:
- Round number
- Tool calls made
- Tool results (truncated if large)
- Stop reason
- Final text returned

### Step 4: Error Handling

Handle these edge cases:
- [ ] API timeout (Claude doesn't respond)
- [ ] Tool execution timeout
- [ ] Invalid tool result format
- [ ] Max rounds exceeded (infinite loop protection)
- [ ] Missing API key
- [ ] Backend (FastAPI) offline

### Step 5: Documentation Updates

- [ ] Update `CLAUDE.md` with new endpoint behavior
- [ ] Document the tool calling loop pattern
- [ ] Add troubleshooting section
- [ ] Update `README.md` session log

---

## Expected Behavior After Fix

### User Types: "Launch Pac-Man"

**Console Output:**
```
[LaunchBox AI] User message: Launch Pac-Man
[LaunchBox AI] Round 1: Calling Claude...
[LaunchBox AI] Round 1 stop_reason: tool_use
[LaunchBox AI] Round 1: 1 tool(s) requested
[LaunchBox AI] Executing tool: search_games { query: 'Pac-Man' }
[LaunchBox AI] Tool result: {"success":true,"count":31,"games":[...]}

[LaunchBox AI] Round 2: Calling Claude...
[LaunchBox AI] Round 2 stop_reason: tool_use
[LaunchBox AI] Round 2: 1 tool(s) requested
[LaunchBox AI] Executing tool: launch_game { game_id: 'pac-man-1980' }
[LaunchBox AI] Tool result: {"success":true,"method_used":"MAME"}

[LaunchBox AI] Round 3: Calling Claude...
[LaunchBox AI] Round 3 stop_reason: end_turn
[LaunchBox AI] Conversation complete after 3 round(s)
```

**LoRa Response:**
```
"🎮 I found 31 Pac-Man games in your library! Launching the 1980 original arcade
version for you. Enjoy this classic maze game!"
```

**Result:**
- ✅ Game launches via MAME
- ✅ User sees friendly confirmation
- ✅ No errors, no white screens

---

## Risk Assessment

### What Could Go Wrong?

1. **Infinite Loop Risk**
   - **Mitigation:** `maxRounds = 10` safety limit
   - **Fallback:** Return partial response if limit hit

2. **Tool Execution Timeout**
   - **Mitigation:** Wrap tool calls in try/catch
   - **Fallback:** Send error as tool_result, let Claude handle it

3. **API Rate Limiting**
   - **Mitigation:** Already using `fetchWithRetry` with backoff
   - **Fallback:** Return error message to user

4. **Message Array Too Large**
   - **Mitigation:** Claude has 200k context window, unlikely to hit
   - **Fallback:** Could implement conversation pruning if needed

5. **Backend Offline**
   - **Mitigation:** Tool functions already handle fetch errors
   - **Fallback:** Claude receives error in tool_result, responds gracefully

### Confidence Level: **9.5/10**

**Why not 10?**
- Haven't tested the exact message format with Anthropic API in production
- Could be edge cases in tool_result formatting

**Why 9.5?**
- The pattern is well-documented by Anthropic
- All infrastructure is already in place
- Only need to refactor one file
- Clear test cases to validate

---

## Next Steps

1. **Review this document** - Confirm the approach makes sense
2. **Implement the fix** - Refactor `launchboxAI.js` with new loop
3. **Test locally** - Verify "Launch Pac-Man" works end-to-end
4. **Document in CLAUDE.md** - Update project docs with new pattern
5. **Consider voice integration** - Once text chat works, voice is just transcription + TTS

---

## Timeline Estimate

- **Implementation:** 1-2 hours
- **Testing:** 30 minutes
- **Documentation:** 30 minutes
- **Total:** 2-3 hours

---

## Future Enhancements (Out of Scope)

These can be added later without changing the core loop:

- Conversation history (store previous turns)
- User preferences (favorite genres, recently played)
- Multi-game launches ("Launch 3 random fighting games")
- Voice input/output integration
- Personality variants (different AI voices)
- Supabase integration for cross-device history

---

**Author:** Claude Code
**Reviewer:** [Your Name]
**Status:** Ready for Implementation
