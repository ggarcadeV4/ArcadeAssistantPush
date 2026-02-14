using System;
using Unbroken.LaunchBox.Plugins;

namespace ArcadeAssistantPlugin
{
    /// <summary>
    /// Main plugin entry point - loads when LaunchBox starts
    /// </summary>
    public class Plugin : ISystemEventsPlugin, IDisposable
    {
        private ArcadeAssistantServer _server;
        private const int PORT = 9999;
        private bool _disposed = false;

        public string Name => "Arcade Assistant Bridge";

            public void OnEventRaised(string eventType)
            {
                try
                {
                    if (eventType == "PluginInitialized")
                    {
                        // Start HTTP server when LaunchBox initializes
                        _server = new ArcadeAssistantServer(PORT);
                        _server.Start();

                        Console.WriteLine($"[Arcade Assistant] Plugin initialized on port {PORT}");
                    }
                    else if (eventType == "LaunchBoxShutdownBeginning")
                    {
                        // Clean shutdown when LaunchBox closes
                        Dispose();
                        Console.WriteLine("[Arcade Assistant] Plugin shutdown complete");
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[Arcade Assistant] Error: {ex.Message}");
                }
            }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        protected virtual void Dispose(bool disposing)
        {
            if (!_disposed)
            {
                if (disposing)
                {
                    _server?.Stop();
                    _server?.Dispose();
                }
                _disposed = true;
            }
        }
    }
}
