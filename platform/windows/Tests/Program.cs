using ATIV.Services;
var client = new EngineClient();
var presets = await client.GetPresetsAsync();
if (presets.Count != 27) throw new Exception("Native client did not decode all presets");
try { await client.ProbeAsync(Path.Combine(Path.GetTempPath(), "ativ-missing-"+Guid.NewGuid()+".wav")); throw new Exception("Missing input unexpectedly succeeded"); }
catch (InvalidOperationException) { }
Console.WriteLine("Native C# process integration passed");

if (args.Length != 1) throw new Exception("Pass the native media fixture directory");
var fixtures = args[0];
var image = Path.Combine(fixtures,"artwork ü.ppm");
var audio = Path.Combine(fixtures,"audio ü.wav");
var duration = await client.ProbeAsync(audio);
if (duration is null || Math.Abs(duration.Value-1)>0.05) throw new Exception("Native duration decode failed");
var preview = Path.Combine(fixtures,"native-preview.png");
await client.PreviewAsync(image,preview,160,90,true,true);
if (!File.Exists(preview)) throw new Exception("Native preview failed");
var video = Path.Combine(fixtures,"native-export.mp4");
var published = false;
await client.RenderAsync(image,audio,video,new ATIV.Models.Preset("Test","16:9",160,90),"128k",30,true,false,item => { if(item.Stage=="complete") published=true; });
if (!published || !File.Exists(video)) throw new Exception("Native export failed");
Console.WriteLine("Native C# probe, preview and export passed");
