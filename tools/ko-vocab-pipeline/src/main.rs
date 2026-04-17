use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use anyhow::{bail, Context, Result};
use bzip2::read::BzDecoder;
use clap::Parser;
use html_escape::decode_html_entities;
use indicatif::{ProgressBar, ProgressStyle};
use quick_xml::events::Event;
use quick_xml::Reader;
use rand::rngs::StdRng;
use rand::SeedableRng;
use rand_distr::{Distribution, StandardNormal};
use rayon::prelude::*;
use regex::Regex;
use serde::Serialize;

const MAX_EMBED_CHUNK_BYTES: usize = 25 * 1024 * 1024;
const OVERSAMPLE: usize = 16;

#[derive(Parser, Debug)]
#[command(about = "Fast Korean Wikipedia analyzer and game-index builder")]
struct Args {
    #[arg()]
    input_path: Option<PathBuf>,

    #[arg(long)]
    all_pages_articles_shards: bool,

    #[arg(long, default_value = "../../data/ko/wikimedia")]
    input_dir: PathBuf,

    #[arg(long, default_value = "../../data/ko/wikimedia/stopwords")]
    stopwords_dir: PathBuf,

    #[arg(long)]
    limit_pages: Option<usize>,

    #[arg(long, default_value_t = 1)]
    min_length: usize,

    #[arg(long, default_value_t = 10)]
    min_count: u32,

    #[arg(long, default_value_t = 1.0)]
    max_doc_ratio: f32,

    #[arg(long, default_value_t = 20_000)]
    max_vocab: usize,

    #[arg(long, default_value_t = 4)]
    window_size: usize,

    #[arg(long, default_value_t = 256)]
    embedding_dim: usize,

    #[arg(long, default_value_t = 2)]
    power_iters: usize,

    #[arg(long, default_value = "100,300,1000,3000,5000,10000,20000,30000,50000")]
    sample_ranks: String,

    #[arg(long, default_value_t = 40)]
    top_freq: usize,

    #[arg(long)]
    output_tsv: Option<PathBuf>,

    #[arg(long)]
    build_output_dir: Option<PathBuf>,
}

#[derive(Default)]
struct LocalCounts {
    term_frequency: HashMap<String, u32>,
    document_frequency: HashMap<String, u32>,
    total_pages: usize,
}

#[derive(Default)]
struct PageRecord {
    title: String,
    namespace: String,
    text: String,
    redirect: bool,
}

struct XmlState {
    page: PageRecord,
    in_revision: bool,
    capture_tag: Option<CaptureTag>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum CaptureTag {
    Title,
    Namespace,
    Text,
}

enum PageAction {
    Continue,
    Stop,
}

struct CountingReader<R> {
    inner: R,
    progress: ProgressBar,
}

impl<R: Read> Read for CountingReader<R> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.inner.read(buf)?;
        if n > 0 {
            self.progress.inc(n as u64);
        }
        Ok(n)
    }
}

struct Cleaner {
    comment: Regex,
    table: Regex,
    magic_word: Regex,
    namespaced_link: Regex,
    wiki_link_with_label: Regex,
    wiki_link_plain: Regex,
    url: Regex,
    html_tag: Regex,
    style_marker: Regex,
    bracket_residue: Regex,
    empty_paren: Regex,
    html_entity_paren: Regex,
    latin_paren: Regex,
    latin_chunk: Regex,
    list_marker: Regex,
    non_text_symbol: Regex,
    multi_punct: Regex,
    heading_equals: Regex,
    drop_tag_wrapped: Regex,
    drop_tag_self_closing: Regex,
    space: Regex,
    leading_junk: Regex,
}

#[derive(Clone)]
struct SelectedToken {
    token: String,
    count: u32,
    doc_frequency: u32,
}

struct BuildState {
    rows: Vec<HashMap<usize, u32>>,
    variants: HashMap<String, HashSet<usize>>,
    total_pages: usize,
}

#[derive(Serialize)]
struct VocabRow<'a> {
    word: &'a str,
    display_word: &'a str,
    count: u32,
    doc_frequency: u32,
}

#[derive(Serialize)]
struct Metadata {
    vocab_size: usize,
    embedding_dim: usize,
    playable_ids: Vec<usize>,
    total_pages: usize,
    min_count: u32,
    max_vocab: usize,
    window_size: usize,
    explained_variance: f32,
    embed_chunks: usize,
    token_unit: &'static str,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let input_paths = resolve_inputs(&args)?;
    let total_bytes = total_input_bytes(&input_paths)?;
    let stopwords = Arc::new(load_stopwords(&args.stopwords_dir)?);
    let cleaner = Arc::new(Cleaner::new()?);
    let sample_ranks = parse_sample_ranks(&args.sample_ranks)?;

    let count_progress = progress_bar(total_bytes, "Counting Korean vocabulary")?;
    let global_page_limit = Arc::new(AtomicUsize::new(0));
    let partials: Vec<Result<LocalCounts>> = input_paths
        .par_iter()
        .map(|path| {
            count_shard(
                path,
                stopwords.clone(),
                cleaner.clone(),
                count_progress.clone(),
                args.limit_pages,
                global_page_limit.clone(),
                args.min_length,
            )
        })
        .collect();
    count_progress.finish_and_clear();

    let mut merged = LocalCounts::default();
    for partial in partials {
        merge_counts(&mut merged, partial?);
    }

    let selected = select_vocab(
        &merged.term_frequency,
        &merged.document_frequency,
        merged.total_pages,
        args.min_count,
        args.max_doc_ratio,
        args.max_vocab,
    );

    println!("Input shards: {}", input_paths.len());
    println!("Pages counted: {}", merged.total_pages);
    println!("Stopwords loaded: {}", stopwords.len());
    println!("Raw word types: {}", merged.term_frequency.len());
    println!("Filtered word types: {}", selected.len());
    print_top_frequency(&selected, args.top_freq);
    print_rank_samples(&selected, &sample_ranks);

    if let Some(output_tsv) = &args.output_tsv {
        write_tsv(output_tsv, &selected)?;
        println!("Wrote {}", output_tsv.display());
    }

    if let Some(output_dir) = &args.build_output_dir {
        let build_progress = progress_bar(total_bytes, "Building Korean cooccurrence")?;
        let build_state = build_state(
            &input_paths,
            stopwords,
            cleaner,
            build_progress.clone(),
            args.limit_pages,
            args.min_length,
            args.window_size,
            &selected,
        )?;
        build_progress.finish_and_clear();
        write_game_artifacts(output_dir, &selected, build_state, &args)?;
        println!("Built game artifacts in {}", output_dir.display());
    }

    Ok(())
}

fn resolve_inputs(args: &Args) -> Result<Vec<PathBuf>> {
    if args.all_pages_articles_shards {
        let mut inputs: Vec<PathBuf> = std::fs::read_dir(&args.input_dir)
            .with_context(|| format!("failed to read {}", args.input_dir.display()))?
            .filter_map(|entry| entry.ok().map(|e| e.path()))
            .filter(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .map(|name| {
                        name.starts_with("kowiki-latest-pages-articles") && name.ends_with(".bz2")
                    })
                    .unwrap_or(false)
            })
            .collect();
        inputs.sort();
        if inputs.is_empty() {
            bail!(
                "no kowiki pages-articles shards found in {}",
                args.input_dir.display()
            );
        }
        return Ok(inputs);
    }
    match &args.input_path {
        Some(path) => Ok(vec![path.clone()]),
        None => bail!("input_path is required unless --all-pages-articles-shards is used"),
    }
}

fn total_input_bytes(paths: &[PathBuf]) -> Result<u64> {
    paths.iter().try_fold(0u64, |sum, path| {
        Ok(sum
            + path
                .metadata()
                .with_context(|| format!("failed to stat {}", path.display()))?
                .len())
    })
}

fn progress_bar(total: u64, message: &str) -> Result<ProgressBar> {
    let progress = ProgressBar::new(total);
    progress.set_style(
        ProgressStyle::with_template(
            "{msg} |{bar:40.cyan/blue}| {bytes}/{total_bytes} [{elapsed_precise}<{eta_precise}, {bytes_per_sec}]",
        )?
        .progress_chars("#>-"),
    );
    progress.set_message(message.to_string());
    Ok(progress)
}

fn load_stopwords(dir: &Path) -> Result<HashSet<String>> {
    let mut stopwords = HashSet::new();
    for entry in
        std::fs::read_dir(dir).with_context(|| format!("failed to read {}", dir.display()))?
    {
        let path = entry?.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("txt") {
            continue;
        }
        let text = std::fs::read_to_string(&path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        for line in text.lines() {
            let word = line.trim();
            if !word.is_empty() {
                stopwords.insert(word.to_string());
            }
        }
    }
    if stopwords.is_empty() {
        bail!("no stopword .txt files found in {}", dir.display());
    }
    Ok(stopwords)
}

impl Cleaner {
    fn new() -> Result<Self> {
        Ok(Self {
            comment: Regex::new(r"(?s)<!--.*?-->")?,
            table: Regex::new(r"(?s)\{\|.*?\|\}")?,
            magic_word: Regex::new(r"__[^_\s]+__")?,
            namespaced_link: Regex::new(
                r"\[\[\s*:?\s*(?:Category|File|Help|Image|Module|Portal|Special|Template|TimedText|Wikipedia|분류|파일|도움말|틀|위키백과)\s*:[^\]]+\]\]",
            )?,
            wiki_link_with_label: Regex::new(r"\[\[[^\]|]+\|([^\]]+)\]\]")?,
            wiki_link_plain: Regex::new(r"\[\[([^\]|]+)\]\]")?,
            url: Regex::new(r"https?://\S+")?,
            html_tag: Regex::new(r"</?[A-Za-z][^>]*>")?,
            style_marker: Regex::new(r"'{2,}")?,
            bracket_residue: Regex::new(r"[\[\]]{2,}")?,
            empty_paren: Regex::new(r"[（(]\s*[)）]")?,
            html_entity_paren: Regex::new(r#"[（(]\s*[A-Za-z0-9 ,;:/._'"-]*\s*[)）]"#)?,
            latin_paren: Regex::new(r"[（(][^()（）]*[A-Za-z][^()（）]*[)）]")?,
            latin_chunk: Regex::new(r#"\b[[:ascii:]][[:ascii:] .,:;/'"_\-]{2,}\b"#)?,
            list_marker: Regex::new(r"(?:^|\s)[*#;:]+")?,
            non_text_symbol: Regex::new(r#"[|<>`~_^]+"#)?,
            multi_punct: Regex::new(r"\s*([，。！？；：、])\s*")?,
            heading_equals: Regex::new(r"={2,}\s*([^=]+?)\s*={2,}")?,
            drop_tag_wrapped: Regex::new(
                r"(?is)<(?:categorytree|charinsert|gallery|graph|imagemap|indicator|math|nowiki|pre|ref|references|score|syntaxhighlight|templatedata|timeline)\b[^>]*?>.*?</(?:categorytree|charinsert|gallery|graph|imagemap|indicator|math|nowiki|pre|ref|references|score|syntaxhighlight|templatedata|timeline)>",
            )?,
            drop_tag_self_closing: Regex::new(
                r"(?is)<(?:categorytree|charinsert|gallery|graph|imagemap|indicator|math|nowiki|pre|ref|references|score|syntaxhighlight|templatedata|timeline)\b[^>]*?/>",
            )?,
            space: Regex::new(r"\s+")?,
            leading_junk: Regex::new(r"^[，。；：、】【\-\s]+")?,
        })
    }

    fn clean(&self, text: &str, title: &str) -> String {
        let mut value = decode_html_entities(text).to_string();
        value = self.comment.replace_all(&value, " ").into_owned();
        value = self.table.replace_all(&value, " ").into_owned();
        value = self.magic_word.replace_all(&value, " ").into_owned();
        value = self.namespaced_link.replace_all(&value, " ").into_owned();
        value = self
            .drop_tag_self_closing
            .replace_all(&value, " ")
            .into_owned();
        value = self.drop_tag_wrapped.replace_all(&value, " ").into_owned();
        value = self
            .wiki_link_with_label
            .replace_all(&value, "$1")
            .into_owned();
        value = self.wiki_link_plain.replace_all(&value, "$1").into_owned();
        value = self.heading_equals.replace_all(&value, " $1 ").into_owned();
        value = self.list_marker.replace_all(&value, " ").into_owned();
        value = self.html_tag.replace_all(&value, " ").into_owned();
        value = self.style_marker.replace_all(&value, " ").into_owned();
        value = self.bracket_residue.replace_all(&value, " ").into_owned();
        value = self.empty_paren.replace_all(&value, " ").into_owned();
        value = self.html_entity_paren.replace_all(&value, " ").into_owned();
        value = self.latin_paren.replace_all(&value, " ").into_owned();
        value = self.latin_chunk.replace_all(&value, " ").into_owned();
        value = self.url.replace_all(&value, " ").into_owned();
        value = self.non_text_symbol.replace_all(&value, " ").into_owned();
        value = self.multi_punct.replace_all(&value, "$1").into_owned();
        value = self.space.replace_all(&value, " ").into_owned();
        let mut value = value.trim().to_string();
        if !title.is_empty() {
            if let Some(anchor) = value.find(title) {
                if anchor > 0 && anchor <= 200 {
                    value = value[anchor..].to_string();
                }
            }
        }
        self.leading_junk.replace_all(&value, "").trim().to_string()
    }
}

fn count_shard(
    path: &Path,
    stopwords: Arc<HashSet<String>>,
    cleaner: Arc<Cleaner>,
    progress: ProgressBar,
    limit_pages: Option<usize>,
    global_page_limit: Arc<AtomicUsize>,
    min_length: usize,
) -> Result<LocalCounts> {
    let mut counts = LocalCounts::default();
    walk_pages(path, progress, |page| {
        process_count_page(
            page,
            &stopwords,
            &cleaner,
            &mut counts,
            min_length,
            limit_pages,
            &global_page_limit,
        )
    })?;
    Ok(counts)
}

fn walk_pages<F>(path: &Path, progress: ProgressBar, mut on_page: F) -> Result<()>
where
    F: FnMut(&PageRecord) -> Result<PageAction>,
{
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let counting_reader = CountingReader {
        inner: file,
        progress,
    };
    let decoder = BzDecoder::new(counting_reader);
    let mut reader = Reader::from_reader(BufReader::new(decoder));
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut state = XmlState {
        page: PageRecord::default(),
        in_revision: false,
        capture_tag: None,
    };
    loop {
        buf.clear();
        match reader.read_event_into(&mut buf)? {
            Event::Start(e) => match e.name().as_ref() {
                b"page" => state.page = PageRecord::default(),
                b"revision" => state.in_revision = true,
                b"title" => state.capture_tag = Some(CaptureTag::Title),
                b"ns" => state.capture_tag = Some(CaptureTag::Namespace),
                b"text" if state.in_revision => state.capture_tag = Some(CaptureTag::Text),
                b"redirect" => state.page.redirect = true,
                _ => {}
            },
            Event::Empty(e) => {
                if e.name().as_ref() == b"redirect" {
                    state.page.redirect = true;
                }
            }
            Event::Text(e) => {
                let text = String::from_utf8_lossy(e.as_ref());
                match state.capture_tag {
                    Some(CaptureTag::Title) => state.page.title.push_str(&text),
                    Some(CaptureTag::Namespace) => state.page.namespace.push_str(&text),
                    Some(CaptureTag::Text) => state.page.text.push_str(&text),
                    None => {}
                }
            }
            Event::CData(e) => {
                if state.capture_tag == Some(CaptureTag::Text) {
                    state
                        .page
                        .text
                        .push_str(&String::from_utf8_lossy(e.as_ref()));
                }
            }
            Event::End(e) => match e.name().as_ref() {
                b"revision" => state.in_revision = false,
                b"title" | b"ns" | b"text" => state.capture_tag = None,
                b"page" => {
                    if matches!(on_page(&state.page)?, PageAction::Stop) {
                        break;
                    }
                }
                _ => {}
            },
            Event::Eof => break,
            _ => {}
        }
    }
    Ok(())
}

fn process_count_page(
    page: &PageRecord,
    stopwords: &HashSet<String>,
    cleaner: &Cleaner,
    counts: &mut LocalCounts,
    min_length: usize,
    limit_pages: Option<usize>,
    global_page_limit: &AtomicUsize,
) -> Result<PageAction> {
    if page.namespace != "0" || page.redirect {
        return Ok(PageAction::Continue);
    }
    if !reserve_page_slot(limit_pages, global_page_limit) {
        return Ok(PageAction::Stop);
    }
    let title_tokens = tokenize_text(&page.title, stopwords, min_length);
    let clean_text = cleaner.clean(&page.text, &page.title);
    let text_tokens = tokenize_text(&clean_text, stopwords, min_length);
    if title_tokens.is_empty() && text_tokens.is_empty() {
        return Ok(PageAction::Continue);
    }
    counts.total_pages += 1;
    let mut seen = HashSet::new();
    for token in title_tokens.into_iter().chain(text_tokens) {
        *counts.term_frequency.entry(token.clone()).or_insert(0) += 1;
        seen.insert(token);
    }
    for token in seen {
        *counts.document_frequency.entry(token).or_insert(0) += 1;
    }
    Ok(PageAction::Continue)
}

fn reserve_page_slot(limit_pages: Option<usize>, global_page_limit: &AtomicUsize) -> bool {
    match limit_pages {
        Some(limit) => global_page_limit.fetch_add(1, Ordering::Relaxed) < limit,
        None => true,
    }
}

fn tokenize_text(text: &str, stopwords: &HashSet<String>, min_length: usize) -> Vec<String> {
    if text.is_empty() {
        return Vec::new();
    }
    let mut tokens = Vec::new();
    let mut current = String::new();
    for ch in text.chars() {
        if is_hangul_char(ch) {
            current.push(ch);
            continue;
        }
        maybe_push_token(&mut tokens, &mut current, stopwords, min_length);
    }
    maybe_push_token(&mut tokens, &mut current, stopwords, min_length);
    tokens
}

fn maybe_push_token(
    tokens: &mut Vec<String>,
    current: &mut String,
    stopwords: &HashSet<String>,
    min_length: usize,
) {
    if current.is_empty() {
        return;
    }
    let token = current.trim();
    if !token.is_empty()
        && token.chars().count() >= min_length
        && !stopwords.contains(token)
        && !is_numeric_only(token)
    {
        tokens.push(token.to_string());
    }
    current.clear();
}

fn is_hangul_char(ch: char) -> bool {
    matches!(
        ch,
        '\u{1100}'..='\u{11FF}'
            | '\u{3130}'..='\u{318F}'
            | '\u{A960}'..='\u{A97F}'
            | '\u{AC00}'..='\u{D7A3}'
            | '\u{D7B0}'..='\u{D7FF}'
    )
}

fn is_numeric_only(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|ch| ch.is_ascii_digit())
}

fn merge_counts(target: &mut LocalCounts, source: LocalCounts) {
    target.total_pages += source.total_pages;
    for (token, count) in source.term_frequency {
        *target.term_frequency.entry(token).or_insert(0) += count;
    }
    for (token, count) in source.document_frequency {
        *target.document_frequency.entry(token).or_insert(0) += count;
    }
}

fn select_vocab(
    term_frequency: &HashMap<String, u32>,
    document_frequency: &HashMap<String, u32>,
    total_pages: usize,
    min_count: u32,
    max_doc_ratio: f32,
    max_vocab: usize,
) -> Vec<SelectedToken> {
    let mut candidates: Vec<SelectedToken> = term_frequency
        .iter()
        .filter_map(|(token, &count)| {
            if count < min_count {
                return None;
            }
            let doc_frequency = document_frequency.get(token).copied().unwrap_or(0);
            if total_pages > 0 && (doc_frequency as f32 / total_pages as f32) > max_doc_ratio {
                return None;
            }
            Some(SelectedToken {
                token: token.clone(),
                count,
                doc_frequency,
            })
        })
        .collect();
    candidates.sort_by(|a, b| {
        b.count
            .cmp(&a.count)
            .then_with(|| b.doc_frequency.cmp(&a.doc_frequency))
            .then_with(|| a.token.cmp(&b.token))
    });
    candidates.truncate(max_vocab);
    candidates
}

fn print_top_frequency(selected: &[SelectedToken], limit: usize) {
    println!("\nTop {limit} words");
    for (index, row) in selected.iter().take(limit).enumerate() {
        println!(
            "{:>6}. {}  count={} doc_frequency={}",
            index + 1,
            row.token,
            row.count,
            row.doc_frequency
        );
    }
}

fn parse_sample_ranks(raw: &str) -> Result<Vec<usize>> {
    let mut ranks = Vec::new();
    for part in raw.split(',') {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        ranks.push(
            part.parse::<usize>()
                .with_context(|| format!("invalid rank: {part}"))?,
        );
    }
    ranks.sort_unstable();
    ranks.dedup();
    Ok(ranks)
}

fn print_rank_samples(selected: &[SelectedToken], ranks: &[usize]) {
    println!("\nRank samples");
    for &rank in ranks {
        if rank == 0 || rank > selected.len() {
            println!("{rank:>6}: out of range (only {} words)", selected.len());
            continue;
        }
        let row = &selected[rank - 1];
        println!(
            "{rank:>6}: {}  count={} doc_frequency={}",
            row.token, row.count, row.doc_frequency
        );
    }
    println!("\nCutoff summary");
    println!(" rank  min_count_at_rank  min_doc_freq_at_rank");
    for &rank in ranks {
        if rank == 0 || rank > selected.len() {
            continue;
        }
        let row = &selected[rank - 1];
        println!(" {rank:>5} {:>18} {:>21}", row.count, row.doc_frequency);
    }
}

fn write_tsv(path: &Path, selected: &[SelectedToken]) -> Result<()> {
    let mut output = String::from("rank\tword\tcount\tdoc_frequency\n");
    for (index, row) in selected.iter().enumerate() {
        output.push_str(&format!(
            "{}\t{}\t{}\t{}\n",
            index + 1,
            row.token,
            row.count,
            row.doc_frequency
        ));
    }
    std::fs::write(path, output).with_context(|| format!("failed to write {}", path.display()))?;
    Ok(())
}

fn build_state(
    input_paths: &[PathBuf],
    stopwords: Arc<HashSet<String>>,
    cleaner: Arc<Cleaner>,
    progress: ProgressBar,
    limit_pages: Option<usize>,
    min_length: usize,
    window_size: usize,
    selected: &[SelectedToken],
) -> Result<BuildState> {
    let token_to_index: HashMap<&str, usize> = selected
        .iter()
        .enumerate()
        .map(|(index, row)| (row.token.as_str(), index))
        .collect();
    let mut state = BuildState {
        rows: vec![HashMap::new(); selected.len()],
        variants: build_variants(selected),
        total_pages: 0,
    };
    let mut processed_pages = 0usize;
    for path in input_paths {
        walk_pages(path, progress.clone(), |page| {
            if page.namespace != "0" || page.redirect {
                return Ok(PageAction::Continue);
            }
            if let Some(limit) = limit_pages {
                if processed_pages >= limit {
                    return Ok(PageAction::Stop);
                }
            }
            let title_tokens = tokenize_text(&page.title, &stopwords, min_length);
            let clean_text = cleaner.clean(&page.text, &page.title);
            let text_tokens = tokenize_text(&clean_text, &stopwords, min_length);
            if title_tokens.is_empty() && text_tokens.is_empty() {
                return Ok(PageAction::Continue);
            }
            processed_pages += 1;
            state.total_pages += 1;
            let mut token_ids = Vec::new();
            for token in &text_tokens {
                if let Some(&token_id) = token_to_index.get(token.as_str()) {
                    token_ids.push(token_id);
                }
            }
            for (index, &token_id) in token_ids.iter().enumerate() {
                let left = index.saturating_sub(window_size);
                let right = (index + window_size + 1).min(token_ids.len());
                let row = &mut state.rows[token_id];
                for neighbor_index in left..right {
                    if neighbor_index == index {
                        continue;
                    }
                    let neighbor_id = token_ids[neighbor_index];
                    if neighbor_id == token_id {
                        continue;
                    }
                    *row.entry(neighbor_id).or_insert(0) += 1;
                }
            }
            Ok(PageAction::Continue)
        })?;
    }
    Ok(state)
}

fn build_variants(selected: &[SelectedToken]) -> HashMap<String, HashSet<usize>> {
    let mut variants = HashMap::new();
    for (token_id, row) in selected.iter().enumerate() {
        add_alias(&mut variants, row.token.as_str(), token_id);
    }
    variants
}

fn add_alias(variants: &mut HashMap<String, HashSet<usize>>, alias: &str, token_id: usize) {
    let trimmed = alias.trim();
    if trimmed.is_empty() {
        return;
    }
    variants
        .entry(trimmed.to_string())
        .or_default()
        .insert(token_id);
}

fn write_game_artifacts(
    output_dir: &Path,
    selected: &[SelectedToken],
    build_state: BuildState,
    args: &Args,
) -> Result<()> {
    std::fs::create_dir_all(output_dir)
        .with_context(|| format!("failed to create {}", output_dir.display()))?;
    let (weighted_rows, kept_old_indices, total_variance) = build_weighted_rows(&build_state.rows);
    let embedding_dim = args
        .embedding_dim
        .min(kept_old_indices.len().saturating_sub(1))
        .min(selected.len().saturating_sub(1))
        .max(2);
    let embeddings = randomized_embeddings(
        &weighted_rows,
        selected.len(),
        embedding_dim,
        args.power_iters,
    )?;
    let normalized_embeddings = normalize_rows(embeddings);
    let kept_selected: Vec<&SelectedToken> = kept_old_indices
        .iter()
        .map(|&index| &selected[index])
        .collect();
    let playable_ids = build_playable_ids(&kept_selected);
    let old_to_new: HashMap<usize, usize> = kept_old_indices
        .iter()
        .enumerate()
        .map(|(new_index, &old_index)| (old_index, new_index))
        .collect();
    let variants = finalize_variants(build_state.variants, &old_to_new);
    let explained_variance =
        explained_variance(&normalized_embeddings.singular_values, total_variance);
    let vocab_rows: Vec<VocabRow<'_>> = kept_selected
        .iter()
        .map(|row| VocabRow {
            word: row.token.as_str(),
            display_word: row.token.as_str(),
            count: row.count,
            doc_frequency: row.doc_frequency,
        })
        .collect();
    std::fs::write(
        output_dir.join("vocab.json"),
        serde_json::to_vec(&vocab_rows)?,
    )?;
    std::fs::write(
        output_dir.join("variants.json"),
        serde_json::to_vec(&variants)?,
    )?;
    let embed_chunks =
        write_embedding_chunks(output_dir, &normalized_embeddings.data, embedding_dim)?;
    let metadata = Metadata {
        vocab_size: kept_selected.len(),
        embedding_dim,
        playable_ids,
        total_pages: build_state.total_pages,
        min_count: args.min_count,
        max_vocab: args.max_vocab,
        window_size: args.window_size,
        explained_variance,
        embed_chunks,
        token_unit: "surface",
    };
    std::fs::write(
        output_dir.join("metadata.json"),
        serde_json::to_vec(&metadata)?,
    )?;
    Ok(())
}

fn build_playable_ids(rows: &[&SelectedToken]) -> Vec<usize> {
    rows.iter()
        .enumerate()
        .filter_map(|(index, row)| {
            if row.token.chars().count() > 6 {
                return None;
            }
            if row.count < 30 || row.doc_frequency < 10 {
                return None;
            }
            Some(index)
        })
        .collect()
}

fn finalize_variants(
    variants: HashMap<String, HashSet<usize>>,
    old_to_new: &HashMap<usize, usize>,
) -> HashMap<String, Vec<usize>> {
    let mut result = HashMap::new();
    for (alias, token_ids) in variants {
        let mut mapped: Vec<usize> = token_ids
            .into_iter()
            .filter_map(|old_index| old_to_new.get(&old_index).copied())
            .collect();
        mapped.sort_unstable();
        mapped.dedup();
        if !mapped.is_empty() {
            result.insert(alias, mapped);
        }
    }
    result
}

fn build_weighted_rows(rows: &[HashMap<usize, u32>]) -> (Vec<Vec<(usize, f32)>>, Vec<usize>, f32) {
    let mut weighted_rows = Vec::new();
    let mut kept_old_indices = Vec::new();
    let mut total_variance = 0.0f32;
    for (old_index, counter) in rows.iter().enumerate() {
        if counter.is_empty() {
            continue;
        }
        let mut row = Vec::with_capacity(counter.len());
        for (&context_index, &count) in counter {
            let value = (1.0 + count as f32).ln();
            total_variance += value * value;
            row.push((context_index, value));
        }
        row.sort_by_key(|(context_index, _)| *context_index);
        weighted_rows.push(row);
        kept_old_indices.push(old_index);
    }
    (weighted_rows, kept_old_indices, total_variance)
}

struct EmbeddingResult {
    data: Vec<f32>,
    singular_values: Vec<f32>,
}

fn randomized_embeddings(
    rows: &[Vec<(usize, f32)>],
    n_features: usize,
    embedding_dim: usize,
    power_iters: usize,
) -> Result<EmbeddingResult> {
    let n_rows = rows.len();
    let rank = (embedding_dim + OVERSAMPLE)
        .min(n_rows.max(embedding_dim + 1))
        .min(n_features.max(embedding_dim + 1));
    let mut rng = StdRng::seed_from_u64(0);
    let normal = StandardNormal;
    let mut omega = vec![0.0f32; n_features * rank];
    for value in &mut omega {
        *value = normal.sample(&mut rng);
    }
    let mut q = orthonormalize(a_times_dense(rows, n_features, &omega, rank), n_rows, rank);
    for _ in 0..power_iters {
        let z = a_transpose_times_dense(rows, n_features, &q, rank);
        q = orthonormalize(a_times_dense(rows, n_features, &z, rank), n_rows, rank);
    }
    let b = qt_times_a(rows, n_features, &q, rank);
    let c = gram_matrix(&b, rank, n_features);
    let (eigenvalues, eigenvectors) = jacobi_eigen_symmetric(c, rank);
    let mut order: Vec<usize> = (0..rank).collect();
    order.sort_by(|&a, &b| eigenvalues[b].partial_cmp(&eigenvalues[a]).unwrap());
    let actual_dim = embedding_dim.min(rank);
    let mut singular_values = Vec::with_capacity(actual_dim);
    let mut embeddings = vec![0.0f32; n_rows * actual_dim];
    for (out_col, &eig_index) in order.iter().take(actual_dim).enumerate() {
        let sigma = eigenvalues[eig_index].max(0.0).sqrt();
        singular_values.push(sigma);
        for row in 0..n_rows {
            let mut value = 0.0f32;
            for k in 0..rank {
                value += q[row * rank + k] * eigenvectors[k * rank + eig_index];
            }
            embeddings[row * actual_dim + out_col] = value * sigma;
        }
    }
    Ok(EmbeddingResult {
        data: embeddings,
        singular_values,
    })
}

fn a_times_dense(
    rows: &[Vec<(usize, f32)>],
    n_features: usize,
    dense: &[f32],
    cols: usize,
) -> Vec<f32> {
    let mut result = vec![0.0f32; rows.len() * cols];
    for (row_index, row) in rows.iter().enumerate() {
        for &(feature_index, value) in row {
            if feature_index >= n_features {
                continue;
            }
            let base = feature_index * cols;
            let out = row_index * cols;
            for col in 0..cols {
                result[out + col] += value * dense[base + col];
            }
        }
    }
    result
}

fn a_transpose_times_dense(
    rows: &[Vec<(usize, f32)>],
    n_features: usize,
    dense: &[f32],
    cols: usize,
) -> Vec<f32> {
    let mut result = vec![0.0f32; n_features * cols];
    for (row_index, row) in rows.iter().enumerate() {
        let dense_row = &dense[row_index * cols..(row_index + 1) * cols];
        for &(feature_index, value) in row {
            let out = feature_index * cols;
            for col in 0..cols {
                result[out + col] += value * dense_row[col];
            }
        }
    }
    result
}

fn orthonormalize(mut matrix: Vec<f32>, rows: usize, cols: usize) -> Vec<f32> {
    for col in 0..cols {
        for prev in 0..col {
            let mut dot = 0.0f32;
            for row in 0..rows {
                dot += matrix[row * cols + col] * matrix[row * cols + prev];
            }
            for row in 0..rows {
                matrix[row * cols + col] -= dot * matrix[row * cols + prev];
            }
        }
        let mut norm = 0.0f32;
        for row in 0..rows {
            let value = matrix[row * cols + col];
            norm += value * value;
        }
        norm = norm.sqrt();
        if norm > 0.0 {
            for row in 0..rows {
                matrix[row * cols + col] /= norm;
            }
        }
    }
    matrix
}

fn qt_times_a(rows: &[Vec<(usize, f32)>], n_features: usize, q: &[f32], rank: usize) -> Vec<f32> {
    let mut result = vec![0.0f32; rank * n_features];
    for (row_index, row) in rows.iter().enumerate() {
        for &(feature_index, value) in row {
            for k in 0..rank {
                result[k * n_features + feature_index] += q[row_index * rank + k] * value;
            }
        }
    }
    result
}

fn gram_matrix(b: &[f32], rows: usize, cols: usize) -> Vec<f32> {
    let mut result = vec![0.0f32; rows * rows];
    for i in 0..rows {
        for j in i..rows {
            let mut dot = 0.0f32;
            for col in 0..cols {
                dot += b[i * cols + col] * b[j * cols + col];
            }
            result[i * rows + j] = dot;
            result[j * rows + i] = dot;
        }
    }
    result
}

fn jacobi_eigen_symmetric(mut a: Vec<f32>, n: usize) -> (Vec<f32>, Vec<f32>) {
    let mut v = vec![0.0f32; n * n];
    for i in 0..n {
        v[i * n + i] = 1.0;
    }
    for _ in 0..(n * n * 20) {
        let mut p = 0usize;
        let mut q = 1usize.min(n.saturating_sub(1));
        let mut max_val = 0.0f32;
        for i in 0..n {
            for j in (i + 1)..n {
                let value = a[i * n + j].abs();
                if value > max_val {
                    max_val = value;
                    p = i;
                    q = j;
                }
            }
        }
        if max_val < 1e-5 {
            break;
        }
        let app = a[p * n + p];
        let aqq = a[q * n + q];
        let apq = a[p * n + q];
        let tau = (aqq - app) / (2.0 * apq);
        let t = if tau >= 0.0 {
            1.0 / (tau + (1.0 + tau * tau).sqrt())
        } else {
            -1.0 / (-tau + (1.0 + tau * tau).sqrt())
        };
        let c = 1.0 / (1.0 + t * t).sqrt();
        let s = t * c;
        for k in 0..n {
            if k != p && k != q {
                let aik = a[k * n + p];
                let akq = a[k * n + q];
                a[k * n + p] = c * aik - s * akq;
                a[p * n + k] = a[k * n + p];
                a[k * n + q] = s * aik + c * akq;
                a[q * n + k] = a[k * n + q];
            }
        }
        a[p * n + p] = c * c * app - 2.0 * s * c * apq + s * s * aqq;
        a[q * n + q] = s * s * app + 2.0 * s * c * apq + c * c * aqq;
        a[p * n + q] = 0.0;
        a[q * n + p] = 0.0;
        for k in 0..n {
            let vip = v[k * n + p];
            let viq = v[k * n + q];
            v[k * n + p] = c * vip - s * viq;
            v[k * n + q] = s * vip + c * viq;
        }
    }
    let eigenvalues = (0..n).map(|i| a[i * n + i]).collect();
    (eigenvalues, v)
}

fn normalize_rows(mut embeddings: EmbeddingResult) -> EmbeddingResult {
    let cols = embeddings.singular_values.len();
    if cols == 0 {
        return embeddings;
    }
    let rows = embeddings.data.len() / cols;
    for row in 0..rows {
        let slice = &mut embeddings.data[row * cols..(row + 1) * cols];
        let norm = slice.iter().map(|v| v * v).sum::<f32>().sqrt();
        if norm > 0.0 {
            for value in slice {
                *value /= norm;
            }
        }
    }
    embeddings
}

fn explained_variance(singular_values: &[f32], total_variance: f32) -> f32 {
    if total_variance <= 0.0 {
        return 0.0;
    }
    singular_values.iter().map(|s| s * s).sum::<f32>() / total_variance
}

fn write_embedding_chunks(
    output_dir: &Path,
    embeddings: &[f32],
    embedding_dim: usize,
) -> Result<usize> {
    let num_words = embeddings.len() / embedding_dim;
    let bytes_per_word = embedding_dim * std::mem::size_of::<f32>();
    let mut words_per_chunk = (MAX_EMBED_CHUNK_BYTES / bytes_per_word).max(1);
    let num_chunks = num_words.div_ceil(words_per_chunk);
    words_per_chunk = num_words.div_ceil(num_chunks.max(1));
    for i in 0..num_chunks {
        let start_word = i * words_per_chunk;
        let end_word = ((i + 1) * words_per_chunk).min(num_words);
        let path = output_dir.join(format!("embeddings.f32.{i}.bin"));
        let mut file =
            File::create(&path).with_context(|| format!("failed to create {}", path.display()))?;
        for value in &embeddings[start_word * embedding_dim..end_word * embedding_dim] {
            file.write_all(&value.to_le_bytes())?;
        }
    }
    Ok(num_chunks)
}
