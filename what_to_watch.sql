select
    yr as 📅,
    category,
    film as 🎬,
    case when is_winner then '☑️' else '' end as '🏆',
    watch_link as 🍿,
    imdb_link as imdb,
    nominee,
    film_id || ',' || film as "movie_comments.csv content"
from nominations.parquet
where film_id not in (select film_id from movie_comments.csv)
order by yr desc, category asc
limit 20;
