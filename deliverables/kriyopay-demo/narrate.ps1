$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$demoNarrator = New-Object System.Speech.Synthesis.SpeechSynthesizer
$demoNarrator.SelectVoice('Microsoft Zira Desktop')
$demoNarrator.Rate = 1
$demoNarrator.Volume = 100
$demoScenes = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'scenes.json') -Raw -Encoding UTF8 | ConvertFrom-Json
for ($demoIndex = 0; $demoIndex -lt $demoScenes.Count; $demoIndex++) {
    $demoAudioPath = Join-Path $PSScriptRoot ('audio/{0:00}.wav' -f $demoIndex)
    $demoNarrator.SetOutputToWaveFile($demoAudioPath)
    $demoNarrator.Speak($demoScenes[$demoIndex].voice)
    $demoNarrator.SetOutputToNull()
    Write-Output ('Narrated scene {0}/15' -f ($demoIndex + 1))
}
$demoNarrator.Dispose()
