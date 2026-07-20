set variable iso_country_code = 'dk';

copy(
  with
    src as (
      select
        *
      from
        read_csv(
          'oscars.csv',
          delim = '	',
          header = true,
          escape = '\',
          quote = '"',
          strict_mode = false,
          ignore_errors = true,
          null_padding = true
        )
    ),
    transform_ as (
      select
        --some early editions would have e.g. 1927/28
        left("year", 4)::int as yr,
        lower("class") as category_type,
        lower(canonicalcategory) as category,
        case
          when category != canonicalcategory then lower(category)
        end as subcategory,
        Film as film,
        'https://www.justwatch.com/' || getvariable('iso_country_code') || '/search?q=' || url_encode (film) as watch_link,
        'https://www.imdb.com/title/' || FilmId as imdb_link,
        name as nominee,
        nominees,
        nomineeIds as nominee_id,
        coalesce(winner, false) as is_winner,
        detail,
        note,
        citation,
        FilmId as film_id
      from
        src
        --filter out early editions where multiple films were nominated simultaneously
        --note "or filmid is null" is also filtered out, but if we can't find it on imdb likely it's difficult finding other places too hence we exclude them here
      where
        FilmId not like '%|%'
    )
  select
    *
  from
    transform_
) to 'nominations.parquet' (format parquet);
