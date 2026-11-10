$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($request.mode -eq 'voices') {
        $voices = @($synth.GetInstalledVoices() | Where-Object Enabled | ForEach-Object {
            @{ name = $_.VoiceInfo.Name; culture = $_.VoiceInfo.Culture.Name; gender = $_.VoiceInfo.Gender.ToString(); provider = 'sapi' }
        })
        ConvertTo-Json -InputObject $voices -Compress
    } else {
        if ($request.voice) { $synth.SelectVoice([string]$request.voice) }
        $synth.Rate = [int]$request.rate
        $synth.Volume = [int]$request.volume
        $buffer = New-Object IO.MemoryStream
        try {
            $synth.SetOutputToWaveStream($buffer)
            $synth.Speak([string]$request.text)
            $synth.SetOutputToNull()
            @{ audio = [Convert]::ToBase64String($buffer.ToArray()) } | ConvertTo-Json -Compress
        } finally { $buffer.Dispose() }
    }
} finally { $synth.Dispose() }
