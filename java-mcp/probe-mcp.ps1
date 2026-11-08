# MCP SSE 探针：验证 Java 服务是否真的按 MCP 协议响应 tools/list。
# 用法：pwsh -File probe-mcp.ps1 [-Endpoints 'http://127.0.0.1:8081/sse','http://127.0.0.1:8082/mcp']
param(
    [string[]]$Endpoints = @('http://127.0.0.1:8081/sse', 'http://127.0.0.1:8082/mcp')
)

foreach ($sseUrl in $Endpoints) {
    Write-Host "`n================ $sseUrl ================" -ForegroundColor Cyan

    $sid = [guid]::NewGuid().ToString('N')
    $req = [System.Net.HttpWebRequest]::Create($sseUrl)
    $req.Method = 'GET'
    $req.Accept = 'text/event-stream'
    $req.Timeout = 15000
    $req.ReadWriteTimeout = 15000
    $req.Headers.Add('x-vercel-protection-bypass', 'none')  # 无害，仅为避免某些代理缓存

    $resp = $null
    $stream = $null
    $reader = $null
    try {
        $resp = $req.GetResponse()
        Write-Host "状态: $([int]$resp.StatusCode) $($resp.StatusCode)  Content-Type: $($resp.ContentType)"
        $stream = $resp.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)

        $endpointPath = $null
        $sw = [System.Diagnostics.Stopwatch]::StartNew()

        while ($sw.Elapsed.TotalSeconds -lt 10) {
            $line = $reader.ReadLine()
            if ($null -eq $line) { break }
            if ($line -like 'event:*') { $curEvent = $line }
            if ($line -like 'data:*') {
                $data = $line.Substring(5).Trim()
                Write-Host "  <- [$($curEvent -replace 'event:\s*','')] $data" -ForegroundColor DarkGray
                if ($data -like '/messages*' -or $data -like 'http*') { $endpointPath = $data }
                if ($data -like '*"result"*' -and $data -like '*tools*') {
                    Write-Host "`n>>> 收到 tools/list 响应：" -ForegroundColor Green
                    $data | ConvertFrom-Json | ConvertTo-Json -Depth 6
                    break
                }
            }
            if ($endpointPath) { break }
        }

        if (-not $endpointPath) {
            Write-Host "未取到 messages 端点（该传输可能使用 /mcp 单一端点，直接 POST 即可）" -ForegroundColor Yellow
            $endpointPath = $sseUrl
        }

        # 组装消息端点
        if ($endpointPath -like 'http*') { $msgUrl = $endpointPath }
        else {
            $b = [uri]$sseUrl
            $msgUrl = "$($b.Scheme)://$($b.Authority)$endpointPath"
        }
        Write-Host "`n消息端点: $msgUrl" -ForegroundColor Cyan

        $send = {
            param($method, $id)
            $body = @{
                jsonrpc = '2.0'
                id      = $id
                method  = $method
                params  = @{}
            }
            if ($method -eq 'initialize') {
                $body.params = @{
                    protocolVersion = '2024-11-05'
                    capabilities    = @{}
                    clientInfo      = @{ name = 'probe'; version = '1.0' }
                }
            }
            if ($method -eq 'tools/list') { $body.params = @{} }
            $json = $body | ConvertTo-Json -Depth 6 -Compress
            Write-Host "  -> $method : $json" -ForegroundColor DarkYellow

            $p = [System.Net.HttpWebRequest]::Create($msgUrl)
            $p.Method = 'POST'
            $p.ContentType = 'application/json'
            $p.Accept = 'application/json, text/event-stream'
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
            $p.ContentLength = $bytes.Length
            $ps = $p.GetRequestStream()
            $ps.Write($bytes, 0, $bytes.Length)
            $ps.Close()
            $pr = $p.GetResponse()
            $sr = New-Object System.IO.StreamReader($pr.GetResponseStream())
            $text = $sr.ReadToEnd()
            Write-Host "  <- HTTP $([int]$pr.StatusCode) $text" -ForegroundColor DarkGray
        }

        & $send 'initialize' 1
        Start-Sleep -Milliseconds 400
        & $send 'tools/list' 2
        Start-Sleep -Milliseconds 1500
    }
    catch {
        Write-Host "错误: $($_.Exception.Message)" -ForegroundColor Red
    }
    finally {
        if ($reader) { $reader.Close() }
        if ($resp) { $resp.Close() }
    }
}
