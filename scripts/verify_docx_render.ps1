$word = New-Object -ComObject Word.Application
$word.Visible = $false
$docPath = "d:\Projects\VitaNexus-RX DDI Major Project\docs\VitaNexus-RX IEEE 2.docx"
$pdfPath = "d:\Projects\VitaNexus-RX DDI Major Project\docs\VitaNexus-RX IEEE 2.pdf"

try {
    $doc = $word.Documents.Open($docPath)
    $pages = $doc.ComputeStatistics(2) # 2 = wdStatisticPages
    $words = $doc.ComputeStatistics(0) # 0 = wdStatisticWords
    $paras = $doc.Paragraphs.Count
    $tables = $doc.Tables.Count
    $shapes = $doc.InlineShapes.Count
    Write-Output "Word Statistics: Pages=$pages, Words=$words, Paragraphs=$paras, Tables=$tables, InlineShapes=$shapes"
    
    $doc.ExportAsFixedFormat($pdfPath, 17) # 17 = wdExportFormatPDF
    Write-Output "Successfully exported PDF to $pdfPath"
    $doc.Close(0) # 0 = wdDoNotSaveChanges
} catch {
    Write-Error $_.Exception.Message
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
