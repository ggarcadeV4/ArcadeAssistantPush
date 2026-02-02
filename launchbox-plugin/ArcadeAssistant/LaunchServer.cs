using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace ArcadeAssistant
{
    /// <summary>
    /// HTTP server for handling game launch requests from WSL/external applications
    /// </summary>
    public class LaunchServer
    {
        private HttpListener _listener;
        private bool _isRunning;
        private readonly string _baseUrl = "http://127.0.0.1:31337/";
        private DateTime _startTime;
        private int _requestCount;
        private readonly JavaScriptSerializer _serializer;

        public TimeSpan Uptime => _isRunning ? DateTime.Now - _startTime : TimeSpan.Zero;
        public int RequestCount => _requestCount;

        public LaunchServer()
        {
            _serializer = new JavaScriptSerializer();
        }

        /// <summary>
        /// Start the HTTP server
        /// </summary>
        public void Start()
        {
            try
            {
                if (_isRunning)
                {
                    return;
                }

                _listener = new HttpListener();
                _listener.Prefixes.Add(_baseUrl);

                // Try to start the listener
                _listener.Start();
                _isRunning = true;
                _startTime = DateTime.Now;

                ArcadeAssistantPlugin.Instance?.LogMessage($"HTTP server started on {_baseUrl}");

                // Main request processing loop
                while (_isRunning)
                {
                    try
                    {
                        // Wait for a request
                        var context = _listener.GetContext();

                        // Process on a thread pool thread
                        ThreadPool.QueueUserWorkItem(_ => ProcessRequest(context));
                    }
                    catch (HttpListenerException ex)
                    {
                        if (_isRunning && ex.ErrorCode != 995) // 995 = operation aborted
                        {
                            ArcadeAssistantPlugin.Instance?.LogError("Listener error", ex);
                        }
                    }
                    catch (Exception ex)
                    {
                        if (_isRunning)
                        {
                            ArcadeAssistantPlugin.Instance?.LogError("Server error", ex);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError("Failed to start HTTP server", ex);
                throw;
            }
        }

        /// <summary>
        /// Stop the HTTP server
        /// </summary>
        public void Stop()
        {
            try
            {
                _isRunning = false;

                if (_listener != null && _listener.IsListening)
                {
                    _listener.Stop();
                    _listener.Close();
                    _listener = null;
                }

                ArcadeAssistantPlugin.Instance?.LogMessage("HTTP server stopped");
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError("Error stopping server", ex);
            }
        }

        /// <summary>
        /// Process an incoming HTTP request
        /// </summary>
        private void ProcessRequest(HttpListenerContext context)
        {
            var request = context.Request;
            var response = context.Response;

            try
            {
                Interlocked.Increment(ref _requestCount);

                // Log request
                ArcadeAssistantPlugin.Instance?.LogMessage(
                    $"Request: {request.HttpMethod} {request.RawUrl} from {request.RemoteEndPoint}");

                // Only accept localhost connections
                if (!IsLocalRequest(request))
                {
                    SendError(response, HttpStatusCode.Forbidden, "Only localhost connections allowed");
                    return;
                }

                // Set CORS headers for localhost
                response.Headers.Add("Access-Control-Allow-Origin", "http://localhost:8787");
                response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                response.Headers.Add("Access-Control-Allow-Headers", "Content-Type, x-scope, x-device-id");

                // Handle OPTIONS preflight
                if (request.HttpMethod == "OPTIONS")
                {
                    response.StatusCode = 200;
                    response.Close();
                    return;
                }

                // Route the request
                switch (request.Url.AbsolutePath.ToLower())
                {
                    case "/":
                    case "/health":
                        HandleHealthCheck(response);
                        break;

                    case "/launch":
                        if (request.HttpMethod == "POST")
                        {
                            HandleLaunch(request, response);
                        }
                        else
                        {
                            SendError(response, HttpStatusCode.MethodNotAllowed, "Only POST allowed");
                        }
                        break;

                    case "/status":
                        HandleStatus(response);
                        break;

                    case "/games":
                        HandleGamesList(response);
                        break;

                    default:
                        SendError(response, HttpStatusCode.NotFound, "Endpoint not found");
                        break;
                }
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError($"Request processing error", ex);
                SendError(response, HttpStatusCode.InternalServerError, "Internal server error");
            }
            finally
            {
                try
                {
                    response.Close();
                }
                catch
                {
                    // Ignore close errors
                }
            }
        }

        /// <summary>
        /// Handle health check endpoint
        /// </summary>
        private void HandleHealthCheck(HttpListenerResponse response)
        {
            var health = new
            {
                available = true,
                version = ArcadeAssistantPlugin.Instance?.Version ?? "1.0.0",
                uptime_seconds = (int)Uptime.TotalSeconds,
                request_count = RequestCount
            };

            SendJsonResponse(response, health);
        }

        /// <summary>
        /// Handle server status endpoint
        /// </summary>
        private void HandleStatus(HttpListenerResponse response)
        {
            var status = ArcadeAssistantPlugin.Instance?.GetStatus();
            if (status != null)
            {
                var statusData = new
                {
                    available = status.Available,
                    version = status.Version,
                    uptime_seconds = (int)status.Uptime.TotalSeconds,
                    request_count = status.RequestCount,
                    timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                };
                SendJsonResponse(response, statusData);
            }
            else
            {
                SendError(response, HttpStatusCode.ServiceUnavailable, "Status unavailable");
            }
        }

        /// <summary>
        /// Handle game launch request
        /// </summary>
        private void HandleLaunch(HttpListenerRequest request, HttpListenerResponse response)
        {
            try
            {
                // Read the request body
                string requestBody;
                using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                {
                    requestBody = reader.ReadToEnd();
                }

                ArcadeAssistantPlugin.Instance?.LogMessage($"Launch request body: {requestBody}");

                // Parse the JSON request
                var launchRequest = _serializer.Deserialize<LaunchRequest>(requestBody);

                if (launchRequest == null || string.IsNullOrWhiteSpace(launchRequest.game_id))
                {
                    SendError(response, HttpStatusCode.BadRequest, "Missing or invalid game_id");
                    return;
                }

                // Launch the game
                var result = ArcadeAssistantPlugin.Instance?.LaunchGame(launchRequest.game_id);

                if (result != null)
                {
                    if (result.Success)
                    {
                        var successResponse = new
                        {
                            launched = true,
                            game_title = result.GameTitle,
                            platform = result.Platform,
                            timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                        };
                        SendJsonResponse(response, successResponse, HttpStatusCode.OK);
                    }
                    else
                    {
                        var errorResponse = new
                        {
                            launched = false,
                            error = result.Error ?? "Unknown error"
                        };
                        SendJsonResponse(response, errorResponse, HttpStatusCode.BadRequest);
                    }
                }
                else
                {
                    SendError(response, HttpStatusCode.ServiceUnavailable, "Plugin not initialized");
                }
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError("Launch request error", ex);
                SendError(response, HttpStatusCode.InternalServerError, $"Launch failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Handle games list endpoint (for testing)
        /// </summary>
        private void HandleGamesList(HttpListenerResponse response)
        {
            try
            {
                // This is a test endpoint to verify game access
                var games = new List<object>();

                // Get a sample of games (first 10)
                var allGames = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetAllGames();
                int count = 0;

                foreach (var game in allGames)
                {
                    if (count >= 10) break;

                    games.Add(new
                    {
                        id = game.Id,
                        title = game.Title,
                        platform = game.Platform,
                        year = game.ReleaseDate?.Year
                    });
                    count++;
                }

                var result = new
                {
                    total = allGames.Count(),
                    sample = games
                };

                SendJsonResponse(response, result);
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError("Games list error", ex);
                SendError(response, HttpStatusCode.InternalServerError, "Failed to retrieve games");
            }
        }

        /// <summary>
        /// Check if request is from localhost
        /// </summary>
        private bool IsLocalRequest(HttpListenerRequest request)
        {
            var remoteEndPoint = request.RemoteEndPoint;
            if (remoteEndPoint == null) return false;

            var address = remoteEndPoint.Address;
            return IPAddress.IsLoopback(address) ||
                   address.Equals(IPAddress.Any) ||
                   address.Equals(IPAddress.IPv6Any);
        }

        /// <summary>
        /// Send a JSON response
        /// </summary>
        private void SendJsonResponse(HttpListenerResponse response, object data, HttpStatusCode statusCode = HttpStatusCode.OK)
        {
            try
            {
                response.StatusCode = (int)statusCode;
                response.ContentType = "application/json; charset=utf-8";

                var json = _serializer.Serialize(data);
                var buffer = Encoding.UTF8.GetBytes(json);

                response.ContentLength64 = buffer.Length;
                response.OutputStream.Write(buffer, 0, buffer.Length);
            }
            catch (Exception ex)
            {
                ArcadeAssistantPlugin.Instance?.LogError("Error sending response", ex);
            }
        }

        /// <summary>
        /// Send an error response
        /// </summary>
        private void SendError(HttpListenerResponse response, HttpStatusCode statusCode, string message)
        {
            var errorResponse = new
            {
                error = message,
                status_code = (int)statusCode,
                timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
            };

            SendJsonResponse(response, errorResponse, statusCode);
        }

        /// <summary>
        /// Launch request model
        /// </summary>
        private class LaunchRequest
        {
            public string game_id { get; set; }
        }
    }
}