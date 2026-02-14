using System;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using ArcadeAssistantPlugin.Models;

namespace ArcadeAssistantPlugin
{
    /// <summary>
    /// Simple HTTP server for Python backend communication
    /// </summary>
    public class ArcadeAssistantServer : IDisposable
    {
        private HttpListener _listener;
        private readonly int _port;
        private bool _isRunning;
        private Task _listenTask;
        private CancellationTokenSource _cancellationTokenSource;

        public ArcadeAssistantServer(int port)
        {
            _port = port;
            _listener = new HttpListener();
            // Bind explicitly to 127.0.0.1 to avoid IPv6/ACL issues
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
            _cancellationTokenSource = new CancellationTokenSource();
        }

        public void Start()
        {
            try
            {
                _listener.Start();
                _isRunning = true;
                Console.WriteLine($"[HTTP Server] Listening on port {_port}");

                // Start listening loop with proper task tracking
                _listenTask = Listen(_cancellationTokenSource.Token);
            }
            catch (HttpListenerException ex)
            {
                Console.WriteLine($"[HTTP Server] Failed to start: {ex.Message}");
                Console.WriteLine("If this is an ACL issue, run (elevated):");
                Console.WriteLine($"  netsh http add urlacl url=http://127.0.0.1:{_port}/ user=Everyone");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[HTTP Server] Failed to start: {ex.Message}");
            }
        }

        public void Stop()
        {
            _isRunning = false;
            _cancellationTokenSource?.Cancel();

            try
            {
                _listener?.Close();
                _listenTask?.Wait(TimeSpan.FromSeconds(5));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[HTTP Server] Error during shutdown: {ex.Message}");
            }

            Console.WriteLine("[HTTP Server] Stopped");
        }

        private async Task Listen(CancellationToken cancellationToken)
        {
            while (_isRunning && _listener.IsListening && !cancellationToken.IsCancellationRequested)
            {
                try
                {
                    var contextTask = _listener.GetContextAsync();
                    var context = await contextTask.ConfigureAwait(false);

                    _ = Task.Run(() => HandleRequest(context), cancellationToken);
                }
                catch (HttpListenerException)
                {
                    break;
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[HTTP Server] Error: {ex.Message}");
                }
            }
        }

        private async Task HandleRequest(HttpListenerContext context)
        {
            var request = context.Request;
            var response = context.Response;

            try
            {
                // Dynamic CORS to reflect origin
                var origin = request.Headers["Origin"];
                if (!string.IsNullOrEmpty(origin) &&
                    (origin == "http://localhost:8787" || origin == "https://localhost:8787"))
                {
                    response.Headers.Add("Access-Control-Allow-Origin", origin);
                }
                else
                {
                    response.Headers.Add("Access-Control-Allow-Origin", "http://localhost:8787");
                }
                response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                response.Headers.Add("Access-Control-Allow-Headers", "Content-Type");

                if (request.HttpMethod == "OPTIONS")
                {
                    response.StatusCode = 200;
                    return;
                }

                Console.WriteLine($"[HTTP Server] {request.HttpMethod} {request.Url.AbsolutePath}");

                switch (request.Url.AbsolutePath)
                {
                    case "/health":
                        await SendJsonResponse(response, new {
                            status = "ok",
                            plugin = "Arcade Assistant Bridge",
                            version = "1.0.0"
                        }).ConfigureAwait(false);
                        break;

                    case "/search-game":
                        var query = request.QueryString["title"];
                        if (string.IsNullOrEmpty(query))
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Missing 'title' parameter" }).ConfigureAwait(false);
                            return;
                        }

                        var games = GameLauncher.SearchGames(query);
                        await SendJsonResponse(response, games).ConfigureAwait(false);
                        break;

                    case "/launch-game":
                        if (request.ContentLength64 == 0)
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                            return;
                        }

                        var body = await ReadRequestBody(request).ConfigureAwait(false);
                        if (string.IsNullOrWhiteSpace(body))
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                            return;
                        }

                        LaunchRequest launchRequest = null;
                        try
                        {
                            launchRequest = JsonSerializer.Deserialize<LaunchRequest>(body);
                        }
                        catch (JsonException ex)
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Invalid JSON", message = ex.Message }).ConfigureAwait(false);
                            return;
                        }

                        var gameId = launchRequest?.GetGameId();
                        if (launchRequest == null || string.IsNullOrEmpty(gameId))
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Invalid request body or missing game ID" }).ConfigureAwait(false);
                            return;
                        }

                        var success = GameLauncher.LaunchGame(gameId);
                        await SendJsonResponse(response, new {
                            success = success,
                            message = success ? "Game launched successfully" : "Failed to launch game"
                        }).ConfigureAwait(false);
                        break;

                    case "/launch":
                        // Backwards-compatible alias for /launch-game
                        // Accepts both { "id": "..." } and { "GameId": "..." }
                        if (request.ContentLength64 == 0)
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                            return;
                        }

                        var launchBody = await ReadRequestBody(request).ConfigureAwait(false);
                        if (string.IsNullOrWhiteSpace(launchBody))
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                            return;
                        }

                        LaunchRequest launchReq = null;
                        try
                        {
                            launchReq = JsonSerializer.Deserialize<LaunchRequest>(launchBody);
                        }
                        catch (JsonException ex)
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Invalid JSON", message = ex.Message }).ConfigureAwait(false);
                            return;
                        }

                        var launchGameId = launchReq?.GetGameId();
                        if (launchReq == null || string.IsNullOrEmpty(launchGameId))
                        {
                            response.StatusCode = 400;
                            await SendJsonResponse(response, new { error = "Invalid request body or missing game ID (provide 'id' or 'GameId')" }).ConfigureAwait(false);
                            return;
                        }

                        var launchSuccess = GameLauncher.LaunchGame(launchGameId);
                        await SendJsonResponse(response, new {
                            success = launchSuccess,
                            message = launchSuccess ? "Game launched successfully" : "Failed to launch game"
                        }).ConfigureAwait(false);
                        break;

                    case "/list-platforms":
                        var platforms = GameLauncher.ListPlatforms();
                        await SendJsonResponse(response, platforms).ConfigureAwait(false);
                        break;

                    case "/list-genres":
                        var genres = GameLauncher.ListGenres();
                        await SendJsonResponse(response, genres).ConfigureAwait(false);
                        break;

                    // ---- Scores Bridge ----
                    case "/scores/by-game":
                        {
                            var gid = request.QueryString["gameId"] ?? request.QueryString["id"];
                            if (string.IsNullOrWhiteSpace(gid))
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Missing 'gameId'" }).ConfigureAwait(false);
                                break;
                            }
                            var list = ScoreService.GetScoresByGame(gid);
                            await SendJsonResponse(response, new { gameId = gid, scores = list }).ConfigureAwait(false);
                            break;
                        }

                    case "/scores/leaderboard":
                        {
                            var limitStr = request.QueryString["limit"];
                            int limit = 10;
                            if (!string.IsNullOrWhiteSpace(limitStr)) int.TryParse(limitStr, out limit);
                            var top = ScoreService.GetLeaderboard(limit <= 0 ? 10 : limit);
                            await SendJsonResponse(response, new { scores = top, count = top.Count }).ConfigureAwait(false);
                            break;
                        }

                    case "/scores/submit":
                        {
                            if (request.ContentLength64 == 0)
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                                break;
                            }
                            var body = await ReadRequestBody(request).ConfigureAwait(false);
                            ScoreSubmitRequest submit;
                            try
                            {
                                submit = JsonSerializer.Deserialize<ScoreSubmitRequest>(body);
                            }
                            catch (JsonException ex)
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Invalid JSON", message = ex.Message }).ConfigureAwait(false);
                                break;
                            }
                            if (submit == null || string.IsNullOrWhiteSpace(submit.GameId) || string.IsNullOrWhiteSpace(submit.Player))
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Missing required fields: gameId, player, score" }).ConfigureAwait(false);
                                break;
                            }
                            if (submit.Score < 0) submit.Score = 0;
                            var entry = ScoreService.AddScore(submit);
                            await SendJsonResponse(response, new { success = true, score = entry }).ConfigureAwait(false);
                            break;
                        }

                    // ---- Event Logging ----
                    case "/events/launch-start":
                    case "/events/launch-end":
                        {
                            if (request.ContentLength64 == 0)
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Empty request body" }).ConfigureAwait(false);
                                break;
                            }
                            var body = await ReadRequestBody(request).ConfigureAwait(false);
                            EventRequest ev;
                            try
                            {
                                ev = JsonSerializer.Deserialize<EventRequest>(body);
                            }
                            catch (JsonException ex)
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Invalid JSON", message = ex.Message }).ConfigureAwait(false);
                                break;
                            }
                            if (ev == null || string.IsNullOrWhiteSpace(ev.GameId))
                            {
                                response.StatusCode = 400;
                                await SendJsonResponse(response, new { error = "Missing 'gameId'" }).ConfigureAwait(false);
                                break;
                            }
                            var type = request.Url.AbsolutePath.EndsWith("launch-start") ? "launch_start" : "launch_end";
                            ScoreService.LogEvent(type, ev);
                            await SendJsonResponse(response, new { success = true }).ConfigureAwait(false);
                            break;
                        }

                    default:
                        response.StatusCode = 404;
                        await SendJsonResponse(response, new { error = "Endpoint not found" }).ConfigureAwait(false);
                        break;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[HTTP Server] Request error: {ex.Message}");
                response.StatusCode = 500;
                try
                {
                    await SendJsonResponse(response, new { error = "Internal server error", message = ex.Message }).ConfigureAwait(false);
                }
                catch
                {
                    // Best effort
                }
            }
            finally
            {
                try
                {
                    response.Close();
                }
                catch
                {
                    // Best effort cleanup
                }
            }
        }

        private async Task<string> ReadRequestBody(HttpListenerRequest request)
        {
            using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
            {
                return await reader.ReadToEndAsync().ConfigureAwait(false);
            }
        }

        private async Task SendJsonResponse(HttpListenerResponse response, object data)
        {
            response.ContentType = "application/json";
            var json = JsonSerializer.Serialize(data, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            });

            var buffer = Encoding.UTF8.GetBytes(json);
            response.ContentLength64 = buffer.Length;

            await response.OutputStream.WriteAsync(buffer, 0, buffer.Length).ConfigureAwait(false);
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (disposing)
            {
                Stop();
                _cancellationTokenSource?.Dispose();
                _listener = null;
            }
        }
    }
}
