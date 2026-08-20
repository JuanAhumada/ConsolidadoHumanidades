using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Windows.Forms;

internal static class Programa
{
    const long MinimoExeReal = 1000000L;
    const string NombreExe = "ConsolidadoHumanidades.exe";
    const string NombreZip = "ConsolidadoHumanidades-Windows.zip";

    [STAThread]
    static void Main()
    {
        try
        {
            Ejecutar();
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                ex.Message,
                "Consolidado de Humanidades",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }

    static void Ejecutar()
    {
        string aqui = AppDirectory();
        string yo = Process.GetCurrentProcess().MainModule.FileName;

        string app = BuscarAplicacion(aqui, yo);
        if (app != null)
        {
            Arrancar(app);
            return;
        }

        string zip = BuscarZip(aqui);
        if (zip != null)
        {
            string dest = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "ConsolidadoHumanidades",
                "app");
            ExtraerSiHaceFalta(zip, dest);
            app = BuscarAplicacion(dest, yo);
            if (app == null)
                app = BuscarAplicacion(Path.Combine(dest, "ConsolidadoHumanidades"), yo);
            if (app != null)
            {
                Arrancar(app);
                return;
            }
        }

        MessageBox.Show(
            "No se encontró la aplicación lista para usar.\n\n" +
            "Descargue ConsolidadoHumanidades-Windows.zip (carpeta release del repositorio), " +
            "extraiga y abra ConsolidadoHumanidades.exe.",
            "Consolidado de Humanidades",
            MessageBoxButtons.OK,
            MessageBoxIcon.Information);
    }

    static string AppDirectory()
    {
        string exe = Process.GetCurrentProcess().MainModule.FileName;
        return Path.GetDirectoryName(Path.GetFullPath(exe));
    }

    static bool EsPaquete(string carpeta)
    {
        if (string.IsNullOrEmpty(carpeta) || !Directory.Exists(carpeta))
            return false;
        string exe = Path.Combine(carpeta, NombreExe);
        if (!File.Exists(exe))
            return false;
        if (new FileInfo(exe).Length < MinimoExeReal)
            return false;
        return Directory.Exists(Path.Combine(carpeta, "_internal"));
    }

    static string BuscarAplicacion(string raiz, string lanzador)
    {
        if (EsPaquete(raiz))
        {
            string exe = Path.GetFullPath(Path.Combine(raiz, NombreExe));
            if (!MismaRuta(exe, lanzador))
                return exe;
        }

        string[] relativas =
        {
            "ConsolidadoHumanidades",
            Path.Combine("dist", "ConsolidadoHumanidades"),
        };
        foreach (string rel in relativas)
        {
            string dir = Path.Combine(raiz, rel);
            if (EsPaquete(dir))
                return Path.GetFullPath(Path.Combine(dir, NombreExe));
        }

        DirectoryInfo padre = Directory.GetParent(raiz);
        if (padre != null)
        {
            string dir = Path.Combine(padre.FullName, "dist", "ConsolidadoHumanidades");
            if (EsPaquete(dir))
                return Path.GetFullPath(Path.Combine(dir, NombreExe));
        }
        return null;
    }

    static string BuscarZip(string raiz)
    {
        string[] candidatos =
        {
            Path.Combine(raiz, NombreZip),
            Path.Combine(raiz, "release", NombreZip),
        };
        DirectoryInfo padre = Directory.GetParent(raiz);
        if (padre != null)
        {
            Array.Resize(ref candidatos, candidatos.Length + 1);
            candidatos[candidatos.Length - 1] = Path.Combine(padre.FullName, "release", NombreZip);
        }
        foreach (string ruta in candidatos)
        {
            if (File.Exists(ruta) && new FileInfo(ruta).Length > MinimoExeReal)
                return ruta;
        }
        return null;
    }

    static void ExtraerSiHaceFalta(string zip, string dest)
    {
        Directory.CreateDirectory(dest);
        string sello = Path.Combine(dest, ".origen_zip");
        string marca = new FileInfo(zip).Length + ":" + new FileInfo(zip).LastWriteTimeUtc.Ticks;
        if (File.Exists(sello) && File.ReadAllText(sello) == marca)
        {
            if (EsPaquete(dest) || EsPaquete(Path.Combine(dest, "ConsolidadoHumanidades")))
                return;
        }

        string temporal = dest + "_tmp";
        if (Directory.Exists(temporal))
            Directory.Delete(temporal, true);
        Directory.CreateDirectory(temporal);
        ZipFile.ExtractToDirectory(zip, temporal);

        if (Directory.Exists(dest))
            Directory.Delete(dest, true);
        Directory.Move(temporal, dest);
        File.WriteAllText(Path.Combine(dest, ".origen_zip"), marca);
    }

    static void Arrancar(string exe)
    {
        var psi = new ProcessStartInfo(exe)
        {
            WorkingDirectory = Path.GetDirectoryName(exe),
            UseShellExecute = true,
        };
        Process.Start(psi);
    }

    static bool MismaRuta(string a, string b)
    {
        return string.Equals(
            Path.GetFullPath(a).TrimEnd('\\'),
            Path.GetFullPath(b).TrimEnd('\\'),
            StringComparison.OrdinalIgnoreCase);
    }
}
