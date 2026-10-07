// SPDX-License-Identifier: GPL-3.0-or-later
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <wincrypt.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <algorithm>
#include <chrono>
#include <thread>
#include <random>

namespace fs = std::filesystem;

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "advapi32.lib")

static std::string randomId() {
    std::random_device rd;
    std::mt19937_64 gen(rd());
    std::uniform_int_distribution<uint64_t> dis;
    std::stringstream ss;
    ss << std::hex << dis(gen) << dis(gen);
    return ss.str();
}

static std::string sha256File(const fs::path &path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return {};

    BCRYPT_ALG_HANDLE hAlg = nullptr;
    if (BCryptOpenAlgorithmProvider(&hAlg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) {
        return {};
    }

    DWORD hashObjectSize = 0, dataSize = 0;
    BCryptGetProperty(hAlg, BCRYPT_OBJECT_LENGTH, (PBYTE)&hashObjectSize, sizeof(DWORD), &dataSize, 0);
    std::vector<BYTE> hashObject(hashObjectSize);

    DWORD hashSize = 0;
    BCryptGetProperty(hAlg, BCRYPT_HASH_LENGTH, (PBYTE)&hashSize, sizeof(DWORD), &dataSize, 0);
    std::vector<BYTE> hash(hashSize);

    BCRYPT_HASH_HANDLE hHash = nullptr;
    if (BCryptCreateHash(hAlg, &hHash, hashObject.data(), hashObjectSize, nullptr, 0, 0) < 0) {
        BCryptCloseAlgorithmProvider(hAlg, 0);
        return {};
    }

    std::vector<char> buffer(65536);
    while (file.read(buffer.data(), buffer.size()) || file.gcount() > 0) {
        BCryptHashData(hHash, (PBYTE)buffer.data(), (ULONG)file.gcount(), 0);
    }

    BCryptFinishHash(hHash, hash.data(), hashSize, 0);
    BCryptDestroyHash(hHash);
    BCryptCloseAlgorithmProvider(hAlg, 0);

    std::stringstream ss;
    for (BYTE b : hash) {
        ss << std::hex << (b < 16 ? "0" : "") << (int)b;
    }
    return ss.str();
}

static int runProcess(const std::wstring &cmd, const std::vector<std::pair<std::wstring, std::wstring>> &envExtra = {}) {
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};

    std::wstring cmdMod = cmd;

    LPVOID envBlock = nullptr;
    if (!envExtra.empty()) {
        LPWCH curEnv = GetEnvironmentStringsW();
        std::vector<std::wstring> envVars;
        if (curEnv) {
            LPCWSTR var = curEnv;
            while (*var) {
                envVars.push_back(var);
                var += wcslen(var) + 1;
            }
            FreeEnvironmentStringsW(curEnv);
        }
        for (const auto &pair : envExtra) {
            std::wstring prefix = pair.first + L"=";
            envVars.erase(std::remove_if(envVars.begin(), envVars.end(),
                [&](const std::wstring &s) { return _wcsnicmp(s.c_str(), prefix.c_str(), prefix.size()) == 0; }),
                envVars.end());
            envVars.push_back(pair.first + L"=" + pair.second);
        }
        std::wstring merged;
        for (const auto &s : envVars) {
            merged += s;
            merged.push_back(L'\0');
        }
        merged.push_back(L'\0');
        envBlock = (LPVOID)merged.data();

        if (!CreateProcessW(nullptr, cmdMod.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                            envBlock, nullptr, &si, &pi)) {
            return -1;
        }
    } else {
        if (!CreateProcessW(nullptr, cmdMod.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW,
                            nullptr, nullptr, &si, &pi)) {
            return -1;
        }
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode = 1;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (int)exitCode;
}

static std::string readJsonValue(const std::string &content, const std::string &key) {
    std::string needle = "\"" + key + "\"";
    auto pos = content.find(needle);
    if (pos == std::string::npos) return {};
    pos = content.find(':', pos + needle.size());
    if (pos == std::string::npos) return {};
    auto start = content.find('"', pos + 1);
    if (start == std::string::npos) return {};
    auto end = content.find('"', start + 1);
    if (end == std::string::npos) return {};
    return content.substr(start + 1, end - start - 1);
}

int wmain(int argc, wchar_t *argv[]) {
    fs::path stage, backup, install;
    bool moved = false;

    try {
        if (argc != 7) {
            throw std::runtime_error("Expected package, signed hash, installation, parent process, target and version.");
        }

        fs::path package = fs::canonical(argv[1]);
        std::string expectedHash;
        {
            std::wstring w = argv[2];
            expectedHash.assign(w.begin(), w.end());
        }
        std::transform(expectedHash.begin(), expectedHash.end(), expectedHash.begin(), ::tolower);

        install = fs::path(argv[3]);
        if (!fs::exists(install) || !fs::is_directory(install) || install.root_path() == install) {
            throw std::runtime_error("Invalid portable installation directory.");
        }

        DWORD pid = std::stoul(argv[4]);
        std::wstring targetStr = argv[5];
        std::wstring versionStr = argv[6];

        std::string actualHash = sha256File(package);
        std::transform(actualHash.begin(), actualHash.end(), actualHash.begin(), ::tolower);
        if (actualHash != expectedHash) {
            throw std::runtime_error("Update bytes changed after authentication.");
        }

        fs::path parent = install.parent_path();
        stage = parent / (".ativ-stage-" + randomId());
        backup = parent / (".ativ-backup-" + randomId());
        fs::create_directories(stage);

        // Extract package using PowerShell Expand-Archive or tar
        std::wstring extractCmd = L"powershell.exe -NoProfile -NonInteractive -Command \"Expand-Archive -LiteralPath '"
            + package.wstring() + L"' -DestinationPath '" + stage.wstring() + L"' -Force\"";
        if (runProcess(extractCmd) != 0) {
            throw std::runtime_error("Failed to extract portable update package.");
        }

        // Validate update-config.json
        fs::path newConfigPath = stage / "update-config.json";
        if (!fs::exists(newConfigPath)) throw std::runtime_error("Missing update-config.json in staged package.");
        std::string newConfig;
        {
            std::ifstream f(newConfigPath);
            std::stringstream ss; ss << f.rdbuf(); newConfig = ss.str();
        }

        std::string targetAscii(targetStr.begin(), targetStr.end());
        std::string versionAscii(versionStr.begin(), versionStr.end());
        if (readJsonValue(newConfig, "target") != targetAscii ||
            readJsonValue(newConfig, "version") != versionAscii ||
            readJsonValue(newConfig, "application_id") != "com.tlolabs.ativ" ||
            readJsonValue(newConfig, "repository") != "tlolabs/ativ" ||
            readJsonValue(newConfig, "channel") != "stable") {
            throw std::runtime_error("Wrong package application, version or target.");
        }

        fs::path oldConfigPath = install / "update-config.json";
        if (fs::exists(oldConfigPath)) {
            std::ifstream f(oldConfigPath);
            std::stringstream ss; ss << f.rdbuf();
            std::string oldConfig = ss.str();
            if (readJsonValue(newConfig, "public_key") != readJsonValue(oldConfig, "public_key")) {
                throw std::runtime_error("Update key rotation requires a bridge release.");
            }
        }

        // Verify required executables
        for (const auto &req : {"ATIV.exe", "ativ-engine.exe", "ativ-update.exe", "ativ-portable-update.exe"}) {
            if (!fs::exists(stage / req)) {
                throw std::runtime_error(std::string("Required application component missing: ") + req);
            }
        }

        // Verify Authenticode signatures
        std::wstring verifyCmd = L"powershell.exe -NoProfile -NonInteractive -Command "
            L"\"$ErrorActionPreference='Stop'; "
            L"$orig=(Get-AuthenticodeSignature -LiteralPath $env:ATIV_ORIGINAL_EXE).SignerCertificate.Subject; "
            L"Get-ChildItem -LiteralPath $env:ATIV_VERIFY_DIR -Recurse -Filter '*.exe' | ForEach-Object { "
            L"  $s=Get-AuthenticodeSignature -LiteralPath $_.FullName; "
            L"  if($s.Status -ne 'Valid' -or !$s.TimeStamperCertificate -or $s.SignerCertificate.Subject -cne $orig) { "
            L"    throw 'Invalid update signature, timestamp or signer' "
            L"  } "
            L"}\"";

        std::vector<std::pair<std::wstring, std::wstring>> envVars = {
            {L"ATIV_VERIFY_DIR", stage.wstring()},
            {L"ATIV_ORIGINAL_EXE", (install / "ATIV.exe").wstring()}
        };
        if (runProcess(verifyCmd, envVars) != 0) {
            throw std::runtime_error("Authenticode verification failed.");
        }

        // Validate engine
        std::wstring checkCmd = L"\"" + (stage / "ativ-engine.exe").wstring() + L"\" check";
        if (runProcess(checkCmd) != 0) {
            throw std::runtime_error("New engine runtime check failed.");
        }

        // Wait for parent process to exit
        HANDLE hParent = OpenProcess(SYNCHRONIZE, FALSE, pid);
        if (hParent) {
            WaitForSingleObject(hParent, 120000);
            CloseHandle(hParent);
        }

        // Preserve user files from old installation
        for (const auto &entry : fs::recursive_directory_iterator(install)) {
            if (fs::is_regular_file(entry)) {
                fs::path rel = fs::relative(entry.path(), install);
                fs::path dest = stage / rel;
                if (!fs::exists(dest)) {
                    fs::create_directories(dest.parent_path());
                    fs::copy_file(entry.path(), dest, fs::copy_options::skip_existing);
                }
            }
        }

        // Atomic swap
        fs::rename(install, backup);
        moved = true;
        fs::rename(stage, install);
        stage.clear();

        // Launch updated application
        std::wstring launchCmd = L"\"" + (install / "ATIV.exe").wstring() + L"\"";
        STARTUPINFOW si{}; si.cb = sizeof(si);
        PROCESS_INFORMATION pi{};
        if (!CreateProcessW(nullptr, launchCmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi)) {
            throw std::runtime_error("Updated application did not launch.");
        }
        WaitForSingleObject(pi.hProcess, 5000);
        DWORD exitCode = 0;
        if (GetExitCodeProcess(pi.hProcess, &exitCode) && exitCode != STILL_ACTIVE) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            throw std::runtime_error("Updated application exited immediately during startup.");
        }
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return 0;

    } catch (const std::exception &ex) {
        std::cerr << "Portable update failed: " << ex.what() << std::endl;
        if (moved && !install.empty() && !backup.empty() && fs::exists(backup)) {
            try {
                if (fs::exists(install)) {
                    fs::rename(install, install.string() + ".failed-" + randomId());
                }
                fs::rename(backup, install);
                std::wstring launchCmd = L"\"" + (install / "ATIV.exe").wstring() + L"\"";
                STARTUPINFOW si{}; si.cb = sizeof(si);
                PROCESS_INFORMATION pi{};
                CreateProcessW(nullptr, launchCmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi);
                if (pi.hProcess) { CloseHandle(pi.hProcess); CloseHandle(pi.hThread); }
            } catch (...) {}
        }
        if (!stage.empty() && fs::exists(stage)) {
            try { fs::remove_all(stage); } catch (...) {}
        }
        return 1;
    }
}
