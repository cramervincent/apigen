import sass
import os

def compile_scss():
    scss_dir = "app/static/scss"
    css_dir = "app/static/css"
    main_scss_file = os.path.join(scss_dir, "main.scss")
    output_css_file = os.path.join(css_dir, "main.css")

    if not os.path.exists(main_scss_file):
        print(f"Waarschuwing: {main_scss_file} niet gevonden. CSS wordt niet gecompileerd.")
        return

    print(f"Compileren van {main_scss_file} naar {output_css_file}...")
    try:
        os.makedirs(css_dir, exist_ok=True)

        css_content = sass.compile(
            filename=main_scss_file,
            output_style='compressed'
        )
        with open(output_css_file, "w") as f:
            f.write(css_content)
        print("SCSS compilatie succesvol.")
    except Exception as e:
        print(f"FOUT bij compileren van SCSS: {e}")

if __name__ == "__main__":
    compile_scss()