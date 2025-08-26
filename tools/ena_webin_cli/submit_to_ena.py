#!/usr/bin/env python3
import os
import sys
import yaml
import subprocess
import shutil
import gzip

def load_credentials(path):
    if os.path.isfile(path):
        with open(path) as f:
            creds = yaml.safe_load(f)
            username = creds.get('username', '').strip()
            password = creds.get('password', '').strip()
            if username and password:
                return username, password
    return None, None

def main():
    # Parse arguments
    (
        user_pref_path, assembly_type, assembly_program, molecule_type, coverage,
        min_gap_length, metadata_format, *rest
    ) = sys.argv[1:]
    
    submit_test = rest[-4].lower() == "true"
    dry_run = rest[-3].lower() == "true"
    log_file = rest[-2]
    outputs_tar = rest[-1]

    # Load credentials
    username, password = load_credentials(user_pref_path)
    if not username or not password:
        global_creds = os.environ.get('GALAXY_ENA_SECRETS', '')
        username, password = load_credentials(global_creds)
        if not username or not password:
            sys.stderr.write("ERROR: No ENA credentials found.\n")
            sys.exit(1)

    workdir = os.getcwd()
    manifests_dir = os.path.join(workdir, "manifests")
    fasta_dir = os.path.join(workdir, "fasta")
    outputs_dir = os.path.join(workdir, "outputs")
    os.makedirs(manifests_dir, exist_ok=True)
    os.makedirs(fasta_dir, exist_ok=True)
    os.makedirs(outputs_dir, exist_ok=True)

    manifest_base = os.path.join(workdir, "manifest_base.tab")
    with open(manifest_base, "w") as mf:
        mf.write(f"ASSEMBLY_TYPE\t{assembly_type}\n")
        mf.write(f"COVERAGE\t{coverage}\n")
        mf.write(f"PROGRAM\t{assembly_program}\n")
        if min_gap_length:
            mf.write(f"MINGAPLENGTH\t{min_gap_length}\n")
        mf.write(f"MOLECULETYPE\t{molecule_type}\n")

    manifests = []
    center_name = None

    if metadata_format == "file":
        ena_receipt, fasta_files = rest[0], rest[1]
        fasta_files = fasta_files.split(",")
        for fasta in fasta_files:
            out_name = os.path.basename(fasta) + ".gz" if not fasta.endswith(".gz") else os.path.basename(fasta)
            out_path = os.path.join(fasta_dir, out_name)
            if not fasta.endswith(".gz"):
                with open(fasta, "rb") as fin, gzip.open(out_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
            else:
                shutil.copy(fasta, out_path)
        # Generate manifests per fasta (placeholder: normally parsed from ena_receipt)
        for fasta in fasta_files:
            mfile = os.path.join(manifests_dir, os.path.basename(fasta) + ".manifest.txt")
            with open(mfile, "w") as mf:
                mf.write(open(manifest_base).read())
                mf.write(f"FASTA\t{os.path.basename(fasta)}\n")
            manifests.append(mfile)
        center_name = "UnknownCenter"  # fallback
    else:
        assembly_name, study_accession, sample_accession, sequencing_platform, description, center_name, genome_fasta = rest[:7]
        generated_manifest = os.path.join(manifests_dir, "generated_manifest.txt")
        with open(generated_manifest, "w") as mf:
            mf.write(open(manifest_base).read())
            mf.write(f"STUDY\t{study_accession}\n")
            mf.write(f"SAMPLE\t{sample_accession}\n")
            mf.write(f"NAME\t{assembly_name}\n")
            mf.write(f"PLATFORM\t{sequencing_platform}\n")
            mf.write(f"FASTA\tconsensus.fasta.gz\n")
        out_path = os.path.join(workdir, "consensus.fasta.gz")
        if not genome_fasta.endswith(".gz"):
            with open(genome_fasta, "rb") as fin, gzip.open(out_path, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        else:
            shutil.copy(genome_fasta, out_path)
        manifests.append(generated_manifest)

    # Run Webin CLI
    with open(log_file, "a") as logf:
        for manifest in manifests:
            logf.write(f"Submitting manifest {manifest}\n")
            cmd = [
                "ena-webin-cli",
                "-context", "genome",
                "-userName", username,
                "-password", password,
                "-centerName", center_name,
                "-manifest", manifest,
                "-inputDir", fasta_dir if metadata_format == "file" else workdir,
                "-outputDir", outputs_dir,
            ]
            if submit_test:
                cmd.append("-test")
            cmd.append("-validate" if dry_run else "-submit")
            subprocess.run(cmd, stdout=logf, stderr=logf, check=False)

    # Package outputs
    subprocess.run(["tar", "-cf", outputs_tar, outputs_dir])

if __name__ == "__main__":
    main()
