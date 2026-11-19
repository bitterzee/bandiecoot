-- Videos for map places and pins: allow video files up to 10 MB in the private media bucket.
update storage.buckets
   set file_size_limit = 10485760,
       allowed_mime_types = array['image/jpeg','image/png','image/webp','video/mp4','video/quicktime','video/webm']
 where id = 'media';
