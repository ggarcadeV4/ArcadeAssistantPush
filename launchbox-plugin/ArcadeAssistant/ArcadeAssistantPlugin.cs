using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Windows.Forms;
using Unbroken.LaunchBox.Plugins;
using Unbroken.LaunchBox.Plugins.Data;

namespace ArcadeAssistant
{
    /// <summary>
    /// Arcade Assistant LaunchBox Plugin - Provides HTTP API for game launching from WSL
    /// </summary>
    public class ArcadeAssistantPlugin : ISystemEventsPlugin, IDisposable
    {
        private LaunchServer _httpServer;
        private Thread _serverThread;
        private bool _isRunning;
        private static ArcadeAssistantPlugin _instance;

        // Plugin metadata
        public string Caption => "Arcade Assistant HTTP Bridge";
        public string Description => "Provides HTTP API for launching games from WSL/external applications";
        public string Author => "Arcade Assistant";
        public string Version => "1.0.0";

        /// <summary>
        /// Gets the singleton instance of the plugin
        /// </summary>
        public static ArcadeAssistantPlugin Instance => _instance;

        /// <summary>
        /// Called when LaunchBox starts up
        /// </summary>
        public void OnEventRaised(string eventType)
        {
            if (eventType == SystemEventTypes.LaunchBoxStartupCompleted)
            {
                Initialize();
            }
            else if (eventType == SystemEventTypes.LaunchBoxShutdownBeginning)
            {
                Shutdown();
            }
        }

        /// <summary>
        /// Initialize the HTTP server
        /// </summary>
        private void Initialize()
        {
            try
            {
                _instance = this;

                LogMessage("Arcade Assistant Plugin initializing...");

                // Create and start the HTTP server
                _httpServer = new LaunchServer();
                _isRunning = true;

                // Run server on a background thread
                _serverThread = new Thread(() =>
                {
                    try
                    {
                        _httpServer.Start();
                    }
                    catch (Exception ex)
                    {
                        LogError($"HTTP server error: {ex.Message}", ex);
                    }
                })
                {
                    Name = "ArcadeAssistant-HTTPServer",
                    IsBackground = true
                };

                _serverThread.Start();

                LogMessage($"Arcade Assistant Plugin v{Version} initialized successfully");
                LogMessage("HTTP API available at http://127.0.0.1:31337/");
            }
            catch (Exception ex)
            {
                LogError("Failed to initialize plugin", ex);
            }
        }

        /// <summary>
        /// Shutdown the HTTP server
        /// </summary>
        private void Shutdown()
        {
            try
            {
                LogMessage("Arcade Assistant Plugin shutting down...");

                _isRunning = false;

                if (_httpServer != null)
                {
                    _httpServer.Stop();
                    _httpServer = null;
                }

                if (_serverThread != null && _serverThread.IsAlive)
                {
                    _serverThread.Join(5000); // Wait max 5 seconds
                    if (_serverThread.IsAlive)
                    {
                        _serverThread.Abort();
                    }
                }

                _instance = null;
                LogMessage("Arcade Assistant Plugin shutdown complete");
            }
            catch (Exception ex)
            {
                LogError("Error during shutdown", ex);
            }
        }

        /// <summary>
        /// Launch a game by ID using LaunchBox API
        /// </summary>
        public LaunchResult LaunchGame(string gameId)
        {
            try
            {
                LogMessage($"Launch request for game ID: {gameId}");

                // Validate GUID format
                if (!IsValidGuid(gameId))
                {
                    return new LaunchResult
                    {
                        Success = false,
                        Error = "Invalid game ID format. Expected GUID."
                    };
                }

                // Find the game using LaunchBox Data Manager
                var game = FindGameById(gameId);
                if (game == null)
                {
                    LogMessage($"Game not found: {gameId}");
                    return new LaunchResult
                    {
                        Success = false,
                        Error = $"Game with ID '{gameId}' not found"
                    };
                }

                LogMessage($"Found game: {game.Title} ({game.Platform})");

                // Launch the game using LaunchBox
                bool launched = LaunchGameInternal(game);

                if (launched)
                {
                    LogMessage($"Successfully launched: {game.Title}");
                    return new LaunchResult
                    {
                        Success = true,
                        GameTitle = game.Title,
                        Platform = game.Platform
                    };
                }
                else
                {
                    LogMessage($"Failed to launch: {game.Title}");
                    return new LaunchResult
                    {
                        Success = false,
                        Error = "LaunchBox failed to start the game"
                    };
                }
            }
            catch (Exception ex)
            {
                LogError($"Error launching game {gameId}", ex);
                return new LaunchResult
                {
                    Success = false,
                    Error = $"Internal error: {ex.Message}"
                };
            }
        }

        /// <summary>
        /// Find a game by its ID
        /// </summary>
        private IGame FindGameById(string gameId)
        {
            try
            {
                // Use LaunchBox Data Manager to get all games
                var allGames = PluginHelper.DataManager.GetAllGames();

                // Find by ID (case-insensitive)
                return allGames.FirstOrDefault(g =>
                    string.Equals(g.Id, gameId, StringComparison.OrdinalIgnoreCase));
            }
            catch (Exception ex)
            {
                LogError("Error accessing game database", ex);
                return null;
            }
        }

        /// <summary>
        /// Launch a game using LaunchBox internal API
        /// </summary>
        private bool LaunchGameInternal(IGame game)
        {
            try
            {
                // Try to use the main view model to launch the game
                if (PluginHelper.LaunchBoxMainViewModel != null)
                {
                    // This needs to be done on the UI thread
                    bool result = false;
                    Exception error = null;

                    var resetEvent = new ManualResetEvent(false);

                    PluginHelper.LaunchBoxMainViewModel.Invoke(() =>
                    {
                        try
                        {
                            PluginHelper.LaunchBoxMainViewModel.PlayGame(game);
                            result = true;
                        }
                        catch (Exception ex)
                        {
                            error = ex;
                            result = false;
                        }
                        finally
                        {
                            resetEvent.Set();
                        }
                    });

                    // Wait for UI thread to complete (max 10 seconds)
                    if (!resetEvent.WaitOne(10000))
                    {
                        LogMessage("Launch operation timed out");
                        return false;
                    }

                    if (error != null)
                    {
                        throw error;
                    }

                    return result;
                }
                else
                {
                    LogMessage("LaunchBox Main View Model not available");
                    return false;
                }
            }
            catch (Exception ex)
            {
                LogError($"Failed to launch game: {game.Title}", ex);
                return false;
            }
        }

        /// <summary>
        /// Get server status information
        /// </summary>
        public ServerStatus GetStatus()
        {
            return new ServerStatus
            {
                Available = _isRunning && _httpServer != null,
                Version = Version,
                Uptime = _httpServer?.Uptime ?? TimeSpan.Zero,
                RequestCount = _httpServer?.RequestCount ?? 0
            };
        }

        /// <summary>
        /// Validate GUID format
        /// </summary>
        private bool IsValidGuid(string input)
        {
            return Guid.TryParse(input, out _);
        }

        /// <summary>
        /// Log an informational message
        /// </summary>
        public void LogMessage(string message)
        {
            try
            {
                var logMessage = $"[ArcadeAssistant] {DateTime.Now:yyyy-MM-dd HH:mm:ss} - {message}";
                System.Diagnostics.Debug.WriteLine(logMessage);

                // Also write to LaunchBox log if available
                if (PluginHelper.DataManager != null)
                {
                    // LaunchBox internal logging (if available)
                    Console.WriteLine(logMessage);
                }
            }
            catch
            {
                // Ignore logging errors
            }
        }

        /// <summary>
        /// Log an error message
        /// </summary>
        public void LogError(string message, Exception ex)
        {
            try
            {
                var errorMessage = $"[ArcadeAssistant ERROR] {DateTime.Now:yyyy-MM-dd HH:mm:ss} - {message}";
                if (ex != null)
                {
                    errorMessage += $"\nException: {ex.GetType().Name}: {ex.Message}\nStack: {ex.StackTrace}";
                }

                System.Diagnostics.Debug.WriteLine(errorMessage);
                Console.Error.WriteLine(errorMessage);
            }
            catch
            {
                // Ignore logging errors
            }
        }

        /// <summary>
        /// Dispose of resources
        /// </summary>
        public void Dispose()
        {
            Shutdown();
        }
    }

    /// <summary>
    /// Result of a game launch operation
    /// </summary>
    public class LaunchResult
    {
        public bool Success { get; set; }
        public string Error { get; set; }
        public string GameTitle { get; set; }
        public string Platform { get; set; }
    }

    /// <summary>
    /// Server status information
    /// </summary>
    public class ServerStatus
    {
        public bool Available { get; set; }
        public string Version { get; set; }
        public TimeSpan Uptime { get; set; }
        public int RequestCount { get; set; }
    }
}