# ============================================================
# doc-gen-system: Phase 4 plan test script
# Usage: edit the 4 values below, then run:  .\run-plan-test.ps1
# ============================================================

$Email          = "sara.pahlevan84@gmail.com"
$Password       = "123456782"
$DeviceDocPath  = "H:\Project\Ali Novin\doc-gen-system\test sample\Input-GUI_VL8.docx"
$ReferenceId    = "e33016e6-f164-4c20-af13-86137a55e96e"   # already-uploaded reference document id
$BaseUrl        = "http://localhost:8000"

function Upload-File($Uri, $Headers, $FilePath) {
    Add-Type -AssemblyName System.Net.Http
    $client = New-Object System.Net.Http.HttpClient
    foreach ($key in $Headers.Keys) {
        $client.DefaultRequestHeaders.TryAddWithoutValidation($key, $Headers[$key]) | Out-Null
    }
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = [System.IO.File]::OpenRead($FilePath)
    $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/octet-stream")
    $fileName = [System.IO.Path]::GetFileName($FilePath)
    $content.Add($fileContent, "file", $fileName)
    $response = $client.PostAsync($Uri, $content).Result
    $body = $response.Content.ReadAsStringAsync().Result
    $fileStream.Close()
    if (-not $response.IsSuccessStatusCode) {
        Write-Host "Upload failed. Status: $($response.StatusCode)"
        Write-Host "Body: $body"
        return $null
    }
    return $body | ConvertFrom-Json
}

Write-Host "`n[1/4] Logging in..." -ForegroundColor Cyan
$login = Invoke-RestMethod -Uri "$BaseUrl/login" -Method Post -ContentType "application/json" `
    -Body (@{email=$Email; password=$Password} | ConvertTo-Json)
$token = $login.access_token
if (-not $token) {
    Write-Host "Login failed - no token received. Response:" -ForegroundColor Red
    $login | ConvertTo-Json
    exit 1
}
$headers = @{ Authorization = "Bearer $token" }
Write-Host "Logged in OK." -ForegroundColor Green

Write-Host "`n[2/4] Uploading device document..." -ForegroundColor Cyan
$deviceUpload = Upload-File -Uri "$BaseUrl/devices/documents" -Headers $headers -FilePath $DeviceDocPath
if (-not $deviceUpload) {
    Write-Host "Device document upload failed - see error above." -ForegroundColor Red
    exit 1
}
$deviceDocId = $deviceUpload.documents[0].id
Write-Host "Device document id: $deviceDocId" -ForegroundColor Green

Write-Host "`n[3/4] Generating chunks + embeddings (this can take a bit)..." -ForegroundColor Cyan
try {
    $chunkResult = Invoke-RestMethod -Uri "$BaseUrl/devices/documents/$deviceDocId/chunks" -Method Post -Headers $headers
    Write-Host "Chunks created: $($chunkResult.chunk_count)" -ForegroundColor Green
} catch {
    Write-Host "Chunk generation failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

Write-Host "`n[4/4] Building plan against reference document $ReferenceId ..." -ForegroundColor Cyan
try {
    $plan = Invoke-RestMethod -Uri "$BaseUrl/rag/reference/$ReferenceId/plan?device_document_id=$deviceDocId" -Method Get -Headers $headers
    $plan | ConvertTo-Json -Depth 5 | Out-File "plan.json" -Encoding utf8
    Write-Host "`nDone. Plan saved to plan.json ($($plan.Count) sections)." -ForegroundColor Green
    Write-Host "Sections with changed=true:" -ForegroundColor Yellow
    $plan | Where-Object { $_.changed -eq $true } | Select-Object section_name, reason, best_similarity | Format-Table -AutoSize
} catch {
    Write-Host "Plan request failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
