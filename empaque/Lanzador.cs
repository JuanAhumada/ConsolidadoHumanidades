using System;
using System.Diagnostics;
using System.Drawing;
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
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            Ejecutar();
        }
        catch (Exception ex)
        {
            MostrarTarjeta("Error", ex.Message, true);
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

        MostrarTarjeta(
            "No se encontró la aplicación",
            "Descargue ConsolidadoHumanidades-Windows.zip (carpeta release), extraiga y abra el ConsolidadoHumanidades.exe de la raíz.",
            true);
    }

    static void MostrarTarjeta(string titulo, string mensaje, bool error)
    {
        Color acento = error ? Color.FromArgb(196, 60, 85) : Color.FromArgb(196, 122, 18);
        var form = new Form
        {
            Text = "Consolidado de Humanidades",
            FormBorderStyle = FormBorderStyle.None,
            StartPosition = FormStartPosition.CenterScreen,
            Size = new Size(460, 250),
            BackColor = Color.FromArgb(243, 246, 249),
            TopMost = true,
        };

        var tarjeta = new Panel
        {
            BackColor = Color.White,
            Location = new Point(22, 22),
            Size = new Size(416, 206),
        };
        var barra = new Panel
        {
            BackColor = acento,
            Location = new Point(0, 0),
            Size = new Size(416, 5),
        };
        var lblTitulo = new Label
        {
            Text = titulo,
            Font = new Font("Segoe UI", 13, FontStyle.Bold),
            ForeColor = Color.FromArgb(10, 22, 40),
            Location = new Point(18, 18),
            Size = new Size(380, 28),
        };
        var lblCuerpo = new Label
        {
            Text = mensaje,
            Font = new Font("Segoe UI", 10),
            ForeColor = Color.FromArgb(90, 107, 125),
            Location = new Point(18, 52),
            Size = new Size(380, 90),
        };
        var btn = new Button
        {
            Text = "Entendido",
            Font = new Font("Segoe UI", 10, FontStyle.Bold),
            ForeColor = Color.White,
            BackColor = acento,
            FlatStyle = FlatStyle.Flat,
            Location = new Point(278, 154),
            Size = new Size(118, 34),
        };
        btn.FlatAppearance.BorderSize = 0;
        btn.Click += delegate { form.Close(); };

        tarjeta.Controls.Add(barra);
        tarjeta.Controls.Add(lblTitulo);
        tarjeta.Controls.Add(lblCuerpo);
        tarjeta.Controls.Add(btn);
        form.Controls.Add(tarjeta);
        form.ShowDialog();
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
            UseShellExecute = false,
            CreateNoWindow = true,
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
