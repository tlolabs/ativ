using ATIV.Services;
var client = new EngineClient();
var presets = await client.GetPresetsAsync();
if (presets.Count != 27) throw new Exception("Native client did not decode all presets");
try { await client.ProbeAsync(Path.Combine(Path.GetTempPath(), "ativ-missing-"+Guid.NewGuid()+".wav")); throw new Exception("Missing input unexpectedly succeeded"); }
catch (InvalidOperationException) { }
Console.WriteLine("Native C# process integration passed");
