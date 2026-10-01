using System.Diagnostics;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;

// Runs outside the installation. A failed verification never changes that directory.
// An unsuccessful launch restores the previous directory. Backups are never deleted.
internal static class Program
{
    private static async Task<int> Main(string[] args)
    {
        string? stage = null, backup = null, install = null;
        bool moved = false;
        try {
            if (args.Length != 5) throw new IOException("Expected package, signed hash, installation, parent process and target.");
            var package = Path.GetFullPath(args[0]); install = Path.TrimEndingDirectorySeparator(Path.GetFullPath(args[2]));
            if (!Directory.Exists(install) || Path.GetPathRoot(install) == install || new DirectoryInfo(install).Attributes.HasFlag(FileAttributes.ReparsePoint))
                throw new IOException("Invalid portable installation directory.");
            if (!args[4].StartsWith("windows-", StringComparison.Ordinal) || args[4] != (System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture == System.Runtime.InteropServices.Architecture.Arm64 ? "windows-arm64" : "windows-x64"))
                throw new IOException("Wrong target update.");
            using (var stream = File.OpenRead(package))
                if (!Convert.ToHexString(SHA256.HashData(stream)).Equals(args[1], StringComparison.OrdinalIgnoreCase)) throw new IOException("Update bytes changed after authentication.");
            var parent = Directory.GetParent(install)?.FullName ?? throw new IOException("Missing installation parent.");
            stage = Path.Combine(parent, ".ativ-stage-"+Guid.NewGuid().ToString("N"));
            backup = Path.Combine(parent, ".ativ-backup-"+Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            var managed = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long total = 0;
            using (var zip = ZipFile.OpenRead(package)) foreach (var entry in zip.Entries) {
                if ((total += entry.Length) > 2L*1024*1024*1024) throw new IOException("Oversized portable package.");
                var name = entry.FullName;
                if (name.Contains('\\') || name.Contains(':') || name.StartsWith('/') || name.Split('/').Any(p => p == ".." || p == ".") || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new IOException("Unsafe portable package entry.");
                var destination = Path.GetFullPath(Path.Combine(stage, name));
                if (!destination.StartsWith(stage+Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new IOException("Package path escapes staging.");
                if (name.EndsWith('/')) { Directory.CreateDirectory(destination); continue; }
                if (!managed.Add(name.Replace('/', Path.DirectorySeparatorChar))) throw new IOException("Duplicate package entry.");
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                entry.ExtractToFile(destination, false);
            }
            var newConfig = JsonDocument.Parse(File.ReadAllText(Path.Combine(stage,"update-config.json"))).RootElement;
            if (newConfig.GetProperty("target").GetString() != args[4]) throw new IOException("Wrong package target.");
            var expected = X509Certificate.CreateFromSignedFile(Path.Combine(install,"ATIV.exe")).Subject;
            var verify = new ProcessStartInfo("powershell.exe") { UseShellExecute=false, CreateNoWindow=true };
            verify.Environment["ATIV_VERIFY_DIR"]=stage; verify.Environment["ATIV_VERIFY_SUBJECT"]=expected;
            verify.ArgumentList.Add("-NoProfile"); verify.ArgumentList.Add("-NonInteractive"); verify.ArgumentList.Add("-Command");
            verify.ArgumentList.Add("$ErrorActionPreference='Stop'; Get-ChildItem -LiteralPath $env:ATIV_VERIFY_DIR -Recurse -Filter '*.exe' | ForEach-Object { $s=Get-AuthenticodeSignature -LiteralPath $_.FullName; if($s.Status -ne 'Valid' -or !$s.TimeStamperCertificate -or $s.SignerCertificate.Subject -cne $env:ATIV_VERIFY_SUBJECT) { throw 'Invalid update signature, timestamp or signer' } }");
            using (var process = Process.Start(verify) ?? throw new IOException("Cannot verify Authenticode.")) { await process.WaitForExitAsync(); if(process.ExitCode!=0) throw new IOException("AuthentiCode verification failed."); }
            var validate = new ProcessStartInfo(Path.Combine(stage,"ativ-engine.exe")) { UseShellExecute=false, CreateNoWindow=true };
            validate.ArgumentList.Add("check"); validate.Environment["PATH"]="";
            using (var process = Process.Start(validate) ?? throw new IOException("Cannot validate new runtime.")) { await process.WaitForExitAsync(); if(process.ExitCode!=0) throw new IOException("New Core runtime failed validation."); }
            try { using var process = Process.GetProcessById(int.Parse(args[3])); await process.WaitForExitAsync().WaitAsync(TimeSpan.FromMinutes(2)); }
            catch (ArgumentException) { /* The old application has already exited. */ }
            var previousManifest = Path.Combine(install,"portable-package-files.json");
            if (File.Exists(previousManifest)) foreach (var name in JsonSerializer.Deserialize<string[]>(File.ReadAllText(previousManifest))!) managed.Add(name);
            // Copy user additions; retain the complete old directory as an additional recovery copy.
            foreach (var directory in Directory.EnumerateDirectories(install,"*",SearchOption.AllDirectories))
                if (new DirectoryInfo(directory).Attributes.HasFlag(FileAttributes.ReparsePoint)) throw new IOException("Linked installation directories require a manual update.");
            foreach (var file in Directory.EnumerateFiles(install,"*",SearchOption.AllDirectories)) {
                if (new FileInfo(file).Attributes.HasFlag(FileAttributes.ReparsePoint)) throw new IOException("Linked installation files require a manual update.");
                var relative = Path.GetRelativePath(install,file);
                if (managed.Contains(relative)) continue;
                var destination=Path.Combine(stage,relative);
                if (File.Exists(destination)) continue;
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!); File.Copy(file,destination,false);
            }
            Directory.Move(install,backup); moved=true;
            Directory.Move(stage,install); stage=null;
            var launch=new ProcessStartInfo(Path.Combine(install,"ATIV.exe")) { UseShellExecute=true };
            using (var process=Process.Start(launch) ?? throw new IOException("Updated application did not launch.")) {
                await Task.Delay(TimeSpan.FromSeconds(5));
                if (process.HasExited) throw new IOException("Updated application exited during startup.");
            }
            return 0;
        } catch (Exception error) {
            if (moved && install != null && backup != null) {
                if (Directory.Exists(install)) Directory.Move(install,install+".failed-"+Guid.NewGuid().ToString("N"));
                Directory.Move(backup,install);
                Process.Start(new ProcessStartInfo(Path.Combine(install,"ATIV.exe")) { UseShellExecute=true });
            }
            Console.Error.WriteLine("Portable update failed; previous installation retained: "+error.Message);
            return 1;
        } finally { if (stage != null && Directory.Exists(stage)) Directory.Delete(stage,true); }
    }
}
