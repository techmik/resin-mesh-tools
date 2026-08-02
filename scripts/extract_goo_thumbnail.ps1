<#
.SYNOPSIS
    Extracts the embedded preview thumbnail from a sliced .goo file (or any
    file Windows Explorer already renders a thumbnail for) as a PNG.

.DESCRIPTION
    .goo is Elegoo Satellite's proprietary sliced-file format -- not a
    standard image and not documented publicly, so it can't be parsed
    directly. But Explorer already shows a thumbnail for it (a shell
    extension installed alongside Satellite knows how to render it), so
    this asks Windows for that same thumbnail via the IShellItemImageFactory
    COM interface instead of trying to reverse-engineer the binary format.
    Confirmed working against a real sliced .goo file -- a from-scratch
    attempt to manually parse the header/pixel data first produced garbage
    (a misread header field claimed a 900-million-pixel image); asking the
    OS for the thumbnail it already knows how to make was the reliable path.

.PARAMETER SourcePath
    Path to the .goo (or other) file to extract a thumbnail from.

.PARAMETER OutPath
    Where to save the resulting PNG.

.PARAMETER Size
    Requested thumbnail size in pixels (square). Default 512. The shell
    may return a smaller cached thumbnail if that's all it has.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File extract_goo_thumbnail.ps1 `
        -SourcePath "C:\Users\YourName\Downloads\some-print.goo" `
        -OutPath "C:\Users\YourName\Documents\preview.png" -Size 512
#>
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$OutPath,
    [int]$Size = 512
)

Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Drawing;

public static class ThumbnailExtractor
{
    [ComImport]
    [Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItemImageFactory
    {
        void GetImage(SIZE size, SIIGBF flags, out IntPtr phbm);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct SIZE { public int cx; public int cy; }

    enum SIIGBF
    {
        SIIGBF_RESIZETOFIT = 0x00,
        SIIGBF_BIGGERSIZEOK = 0x01,
        SIIGBF_MEMORYONLY = 0x02,
        SIIGBF_ICONONLY = 0x04,
        SIIGBF_THUMBNAILONLY = 0x08,
        SIIGBF_INCACHEONLY = 0x10
    }

    [DllImport("shell32.dll")]
    static extern int SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string path,
        IntPtr pbc,
        ref Guid riid,
        out IShellItemImageFactory ppv);

    [DllImport("gdi32.dll")]
    static extern bool DeleteObject(IntPtr hObject);

    public static void SaveThumbnail(string path, string outPath, int size)
    {
        Guid guid = typeof(IShellItemImageFactory).GUID;
        IShellItemImageFactory factory;
        int hr = SHCreateItemFromParsingName(path, IntPtr.Zero, ref guid, out factory);
        if (hr != 0)
        {
            throw new Exception("SHCreateItemFromParsingName failed, hresult=" + hr);
        }
        IntPtr hBitmap;
        factory.GetImage(new SIZE { cx = size, cy = size }, SIIGBF.SIIGBF_THUMBNAILONLY, out hBitmap);
        try
        {
            using (Bitmap bmp = Bitmap.FromHbitmap(hBitmap))
            {
                bmp.Save(outPath, System.Drawing.Imaging.ImageFormat.Png);
            }
        }
        finally
        {
            DeleteObject(hBitmap);
        }
    }
}
"@

[ThumbnailExtractor]::SaveThumbnail($SourcePath, $OutPath, $Size)
Write-Output "OK: $OutPath"
